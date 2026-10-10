"""Restrict a Zapret preset to the traffic of a single VPN server.

When a server is bound to a preset ("run together with server"), the bound
preset must only touch the connection to that server, while the preset the
user started by hand keeps working for everything else.  winws2 supports
several profiles in one process (separated by ``--new``, first match wins),
so both strategies run in a single winws2 instance:

    <merged global options> <server profiles> --new <manual profiles>

A server is bound either to a dedicated server strategy (``@server[:<id>]``:
a strategy from the winws2 catalog of its kind -- TCP, QUIC or WireGuard, see
:mod:`.zapret_strategies`) or to a preset. A preset becomes
server profiles by replacing its own targets (hostlists / ipsets / L7 filters)
with ``--ipset-ip=<server IPs>`` and the server port, so it never matches other
traffic.
"""

from __future__ import annotations

import ipaddress
import re
import socket
import threading
import time
from dataclasses import dataclass
from typing import Any, Iterable

from . import bootstrap_dns
from .zapret_strategies import (
    KIND_TRANSPORT,
    SERVER_STRATEGY_PRESET,
    is_server_strategy,
    node_server_kind,
    server_strategy_id,
    strategy_for,
    strategy_global_args,
)

# Options that configure the winws2 process as a whole rather than a profile.
_GLOBAL_PREFIXES = ("--lua-init", "--lua-gc", "--blob", "--wf-", "--ctrack-", "--ipcache-", "--debug")
# WinDivert port filters: merged into one option per key.
_WF_PORT_KEYS = ("--wf-tcp-out", "--wf-udp-out", "--wf-tcp-in", "--wf-udp-in")
# Profile target filters that are replaced by the server IP filter.
_TARGET_PREFIXES = ("--hostlist", "--ipset", "--filter-l7", "--name")
_POSITIVE_TARGETS = ("--hostlist=", "--hostlist-domains=", "--ipset=", "--ipset-ip=", "--hostlist-auto=")

# Server profiles only touch connection handshakes: a desync applied to the
# data of a live VPN session ("--payload=all" in most presets) corrupts it.
_TCP_HANDSHAKE_PAYLOAD = "tls_client_hello,http_req"
_UDP_HANDSHAKE_PAYLOAD = "quic_initial,wireguard_initiation"
_DESYNC_PAYLOAD_RE = re.compile(r":payload=[^:]*")

_UDP_PROTOCOLS = {"hysteria", "hysteria2", "hy2", "tuic", "wireguard", "wg", "warp", "awg", "amneziawg"}
_UDP_NETWORKS = {"kcp", "mkcp", "quic"}


@dataclass(frozen=True)
class ZapretServerScope:
    """Bound preset limited to one server endpoint."""

    preset: str
    ips: tuple[str, ...]
    port: int
    label: str = ""
    tcp: bool = True
    udp: bool = False
    node_id: str = ""
    # Dedicated server strategy (preset == SERVER_STRATEGY_PRESET).
    kind: str = ""
    strategy: str = ""
    strategy_name: str = ""
    strategy_args: tuple[str, ...] = ()

    @property
    def uses_strategy(self) -> bool:
        return self.preset == SERVER_STRATEGY_PRESET

    @property
    def title(self) -> str:
        if self.uses_strategy:
            return f"стратегия {self.strategy_name or self.strategy}"
        return f"пресет {self.preset}"

    def signature(self) -> tuple:
        """What winws2 does with the server (addresses excluded)."""
        return (self.node_id, self.preset, self.strategy, self.strategy_args, self.port, self.tcp, self.udp)

    def describe(self) -> str:
        target = ", ".join(self.ips)
        return f"{self.label or target} ({target}:{self.port})"


def _option_key(arg: str) -> str:
    return str(arg).split("=", 1)[0]


def _option_value(arg: str) -> str:
    parts = str(arg).split("=", 1)
    return parts[1] if len(parts) == 2 else ""


def is_global_option(arg: str) -> bool:
    return str(arg).startswith(_GLOBAL_PREFIXES)


def split_preset_args(args: Iterable[str]) -> tuple[list[str], list[list[str]]]:
    """Split winws2 argv into global options and ``--new`` separated profiles."""
    global_args: list[str] = []
    profiles: list[list[str]] = [[]]
    for raw in args:
        arg = str(raw or "").strip()
        if not arg:
            continue
        if arg == "--new":
            profiles.append([])
        elif is_global_option(arg):
            global_args.append(arg)
        else:
            profiles[-1].append(arg)
    return global_args, [profile for profile in profiles if profile]


def _port_ranges(spec: str) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    for item in str(spec or "").split(","):
        item = item.strip()
        if not item:
            continue
        low, _, high = item.partition("-")
        try:
            start = int(low)
            end = int(high) if high else start
        except ValueError:
            continue
        ranges.append((min(start, end), max(start, end)))
    return ranges


def port_spec_covers(spec: str, port: int) -> bool:
    return any(start <= port <= end for start, end in _port_ranges(spec))


def _merge_port_specs(specs: Iterable[str]) -> str:
    items: list[str] = []
    for spec in specs:
        for item in str(spec or "").split(","):
            item = item.strip()
            if item and item not in items:
                items.append(item)
    return ",".join(items)


def merge_global_args(*groups: Iterable[str], extra_ports: dict[str, int] | None = None) -> list[str]:
    """Merge the global options of several presets without duplicates.

    ``--blob`` is deduplicated by name and single-value options keep their
    first occurrence; WinDivert port filters are merged into one option and
    ``extra_ports`` (e.g. the server port) is added to them.
    """
    merged: list[str] = []
    seen: set[str] = set()
    blob_names: set[str] = set()
    single_keys: set[str] = set()
    wf_ports: dict[str, list[str]] = {}
    wf_positions: dict[str, int] = {}
    for group in groups:
        for arg in group:
            key = _option_key(arg)
            if key in _WF_PORT_KEYS:
                if key not in wf_positions:
                    wf_positions[key] = len(merged)
                    merged.append(key)
                wf_ports.setdefault(key, []).append(_option_value(arg))
                continue
            if arg in seen:
                continue
            if key == "--blob":
                name = _option_value(arg).split(":", 1)[0]
                if name in blob_names:
                    continue
                blob_names.add(name)
            elif key.startswith(("--ctrack-", "--ipcache-", "--lua-gc", "--debug")):
                if key in single_keys:
                    continue
                single_keys.add(key)
            seen.add(arg)
            merged.append(arg)
    for key, port in (extra_ports or {}).items():
        if key not in _WF_PORT_KEYS or port <= 0:
            continue
        specs = wf_ports.setdefault(key, [])
        if not any(port_spec_covers(spec, port) for spec in specs):
            specs.append(str(port))
        if key not in wf_positions:
            wf_positions[key] = len(merged)
            merged.append(key)
    for key, index in wf_positions.items():
        merged[index] = f"{key}={_merge_port_specs(wf_ports.get(key, []))}"
    return merged


def _profile_desyncs(profile: list[str]) -> list[str]:
    return [_option_value(arg) for arg in profile if _option_key(arg) == "--lua-desync"]


def _is_pass_profile(profile: list[str]) -> bool:
    desyncs = _profile_desyncs(profile)
    return not desyncs or all(value.split(":", 1)[0].strip() == "pass" for value in desyncs)


def scope_profile(profile: list[str], scope: ZapretServerScope, *, name: str) -> list[str] | None:
    """Rewrite one preset profile so it only matches the server endpoint."""
    if _is_pass_profile(profile):
        return None
    tcp_spec = next((_option_value(a) for a in profile if _option_key(a) == "--filter-tcp"), None)
    udp_spec = next((_option_value(a) for a in profile if _option_key(a) == "--filter-udp"), None)
    use_tcp = scope.tcp and (tcp_spec is not None or udp_spec is None)
    use_udp = scope.udp and (udp_spec is not None or tcp_spec is None)
    if not use_tcp and not use_udp:
        return None
    payload = ",".join(
        value for value, enabled in ((_TCP_HANDSHAKE_PAYLOAD, use_tcp), (_UDP_HANDSHAKE_PAYLOAD, use_udp)) if enabled
    )
    body = [
        _handshake_only(arg, payload)
        for arg in profile
        if not _option_key(arg).startswith(_TARGET_PREFIXES)
        and _option_key(arg) not in ("--filter-tcp", "--filter-udp", "--payload")
    ]
    result = [f"--name={name}"]
    if use_tcp:
        result.append(f"--filter-tcp={scope.port}")
    if use_udp:
        result.append(f"--filter-udp={scope.port}")
    result.append("--ipset-ip=" + ",".join(scope.ips))
    result.append(f"--payload={payload}")
    result.extend(body)
    return result


def _handshake_only(arg: str, payload: str) -> str:
    if _option_key(arg) != "--lua-desync":
        return arg
    return _DESYNC_PAYLOAD_RE.sub(f":payload={payload}", arg)


def _profile_rank(profile: list[str], scope: ZapretServerScope) -> tuple[int, int]:
    targeted = any(str(arg).startswith(_POSITIVE_TARGETS) for arg in profile)
    specs = [_option_value(a) for a in profile if _option_key(a) in ("--filter-tcp", "--filter-udp")]
    covered = not specs or any(port_spec_covers(spec, scope.port) for spec in specs)
    return (1 if targeted else 0, 0 if covered else 1)


def build_server_profiles(server_args: Iterable[str], scope: ZapretServerScope) -> tuple[list[str], list[list[str]]]:
    """Global options and server-only profiles built from the bound preset.

    Generic strategies ("all sites") go first, then service specific ones;
    exclusion profiles (``pass``) are dropped because they would shadow the
    strategy for the server.
    """
    global_args, profiles = split_preset_args(server_args)
    ranked = sorted(
        enumerate(profiles),
        key=lambda item: (*_profile_rank(item[1], scope), item[0]),
    )
    label = scope.label or scope.ips[0]
    result: list[list[str]] = []
    seen: set[tuple[str, ...]] = set()
    for _, profile in ranked:
        scoped = scope_profile(profile, scope, name=f"Lumen server: {label}")
        if scoped is None:
            continue
        marker = tuple(scoped[1:])
        if marker in seen:
            continue
        seen.add(marker)
        result.append(scoped)
    for index, profile in enumerate(result):
        profile[0] = f"--name=Lumen server: {label} #{index + 1}"
    return global_args, result


def build_strategy_profiles(scope: ZapretServerScope) -> tuple[list[str], list[list[str]]]:
    """Global options and the single server profile of a dedicated strategy."""
    args = tuple(scope.strategy_args)
    if not args or not scope.ips:
        return [], []
    # A "pass" strategy is kept on purpose: the server's packets are then left
    # alone even when the manual preset would touch them.
    transport = "udp" if scope.udp else "tcp"
    label = scope.label or scope.ips[0]
    profile = [
        f"--name=Lumen server: {label}",
        f"--filter-{transport}={scope.port}",
        "--ipset-ip=" + ",".join(scope.ips),
        *args,
    ]
    return list(strategy_global_args(args)), [profile]


def build_scoped_args(
    server_args: Iterable[str],
    scope: ZapretServerScope,
    manual_args: Iterable[str] | None = None,
) -> list[str]:
    """winws2 argv: server-only profiles first, then the manual preset."""
    if scope.uses_strategy:
        server_globals, server_profiles = build_strategy_profiles(scope)
    else:
        server_globals, server_profiles = build_server_profiles(server_args, scope)
    manual_globals, manual_profiles = split_preset_args(manual_args or [])
    if not server_profiles:
        return []
    extra_ports: dict[str, int] = {}
    if scope.tcp:
        extra_ports["--wf-tcp-out"] = scope.port
    if scope.udp:
        extra_ports["--wf-udp-out"] = scope.port
    args = merge_global_args(server_globals, manual_globals, extra_ports=extra_ports)
    profiles = server_profiles + manual_profiles
    for index, profile in enumerate(profiles):
        if index:
            args.append("--new")
        args.extend(profile)
    return args


def node_transports(node: Any) -> tuple[bool, bool]:
    """(tcp, udp) used by the node to reach its server."""
    outbound = getattr(node, "outbound", None) or {}
    protocol = str(
        (outbound.get("protocol") or outbound.get("type")) if isinstance(outbound, dict) else ""
    ).strip().lower()
    protocol = protocol or str(getattr(node, "scheme", "") or "").strip().lower()
    stream = outbound.get("streamSettings") if isinstance(outbound, dict) else None
    network = str((stream or {}).get("network") or "").strip().lower() if isinstance(stream, dict) else ""
    if protocol in _UDP_PROTOCOLS or network in _UDP_NETWORKS:
        return False, True
    return True, False


def make_server_scope(
    node: Any,
    preset: str,
    ips: Iterable[str],
) -> ZapretServerScope | None:
    """Scope for a bound node; None without an address or a usable strategy."""
    host, port = node_endpoint(node)
    ip_list = tuple(ips)
    if not port or not ip_list:
        return None
    node_id = str(getattr(node, "id", "") or "")
    label = str(getattr(node, "name", "") or host or node_id)
    if is_server_strategy(preset):
        kind = node_server_kind(node)
        strategy = strategy_for(kind, server_strategy_id(preset))
        if strategy is None:
            return None
        udp = KIND_TRANSPORT.get(kind) == "udp"
        return ZapretServerScope(
            preset=SERVER_STRATEGY_PRESET, ips=ip_list, port=port, label=label, tcp=not udp, udp=udp, node_id=node_id,
            kind=kind, strategy=strategy.strategy_id, strategy_name=strategy.name, strategy_args=strategy.args,
        )
    tcp, udp = node_transports(node)
    return ZapretServerScope(preset=preset, ips=ip_list, port=port, label=label, tcp=tcp, udp=udp, node_id=node_id)


def node_endpoint(node: Any) -> tuple[str, int]:
    host = str(getattr(node, "server", "") or "").strip().strip("[]")
    try:
        port = int(getattr(node, "port", 0) or 0)
    except (TypeError, ValueError):
        port = 0
    return host, port if 0 < port < 65536 else 0


def _is_usable_ip(value: str) -> bool:
    return bootstrap_dns.usable_address(value)


_RESOLVE_CACHE: dict[str, tuple[float, tuple[str, ...]]] = {}
_RESOLVE_LOCK = threading.Lock()
_RESOLVE_CACHE_TTL = 24 * 3600.0


def _trusted_doh(host: str) -> set[str]:
    return bootstrap_dns.resolve_doh(host, timeout=2.5)


def _system_lookup(host: str) -> set[str]:
    found: set[str] = set()
    for info in socket.getaddrinfo(host, None, 0, socket.SOCK_STREAM):
        address = str(info[4][0]).split("%", 1)[0] if info and info[4] else ""
        if _is_usable_ip(address):
            found.add(str(ipaddress.ip_address(address)))
    return found


def _ordered(addresses: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted(set(addresses), key=lambda a: (":" in a, a)))


def cached_server_ips(host: str) -> tuple[str, ...]:
    """IP literal or the last real answer for the host, without any lookup."""
    host = str(host or "").strip().strip("[]").rstrip(".")
    if not host:
        return ()
    if _is_usable_ip(host):
        return (str(ipaddress.ip_address(host)),)
    with _RESOLVE_LOCK:
        cached = _RESOLVE_CACHE.get(host.lower())
    if cached and time.monotonic() - cached[0] < _RESOLVE_CACHE_TTL:
        return cached[1]
    return ()


def resolve_server_ips(host: str) -> tuple[str, ...]:
    """Real IP addresses of the server (blocking; call from a worker).

    Trusted DoH by literal resolver IP first (ISP DNS may lie about blocked
    names), then the system resolver (fake-ip answers of TUN mode are
    ignored), then the last address learned over DoH (persistent, up to
    7 days) and finally the last answer of this session.
    """
    host = str(host or "").strip().strip("[]").rstrip(".")
    if not host:
        return ()
    if _is_usable_ip(host):
        return (str(ipaddress.ip_address(host)),)
    key = host.lower()
    try:
        resolution = bootstrap_dns.resolve_bootstrap(host, doh=_trusted_doh, system=_system_lookup)
        ips = _ordered(resolution.addresses)
    except bootstrap_dns.BootstrapNameNotFound:
        return ()
    except OSError:
        ips = ()
    now = time.monotonic()
    with _RESOLVE_LOCK:
        if ips:
            _RESOLVE_CACHE[key] = (now, ips)
            return ips
        cached = _RESOLVE_CACHE.get(key)
        if cached and now - cached[0] < _RESOLVE_CACHE_TTL:
            return cached[1]
    return ()
