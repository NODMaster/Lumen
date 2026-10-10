"""Trusted resolution of a VPN server name before the tunnel is up.

Ported from ZapretKVN. The system resolver of many ISPs answers NXDOMAIN or a
stub address for blocked names and plain DNS to public resolvers is
intercepted, so the server name is first asked over DoH from several
resolvers addressed by literal IP (no SNI is sent for an IP, the certificate
is checked against the IP SAN). Then the system resolver is tried, and as a
last resort the last address obtained over DoH (kept for up to seven days;
system answers are never stored because they may be forged).
"""

from __future__ import annotations

import http.client
import ipaddress
import json
import os
import socket
import struct
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

from .http_utils import get_ssl_context

#: Resolvers whose certificates carry the IP in SAN (HTTP/1.1 DoH).
DOH_SERVERS: tuple[str, ...] = ("8.8.8.8", "1.1.1.1", "94.140.14.14", "8.8.4.4", "1.0.0.1")
DOH_PATH = "/dns-query"
CACHE_MAX_AGE_SEC = 7 * 24 * 3600

_TYPE_A = 1
_TYPE_AAAA = 28
_RCODE_NXDOMAIN = 3


class BootstrapDnsError(OSError):
    """No trusted resolver answered."""


class BootstrapNameNotFound(BootstrapDnsError):
    """Trusted resolvers confirmed that the name does not exist."""


@dataclass(frozen=True)
class BootstrapResolution:
    addresses: frozenset[str]
    source: str  # "literal" | "doh" | "system" | "cache"


def normalize_host(host: str) -> str:
    return str(host or "").strip().strip("[]").rstrip(".").lower()


def build_query(name: str, qtype: int) -> bytes:
    labels = normalize_host(name).encode("idna").split(b".")
    question = b"".join(bytes([len(label)]) + label for label in labels if label) + b"\x00"
    # ID 0 as RFC 8484 recommends (cache friendly).
    return struct.pack("!HHHHHH", 0, 0x0100, 1, 0, 0, 0) + question + struct.pack("!HH", qtype, 1)


def _skip_name(payload: bytes, offset: int) -> int:
    while True:
        length = payload[offset]
        if length & 0xC0 == 0xC0:
            return offset + 2
        if length == 0:
            return offset + 1
        offset += 1 + length


def parse_response(payload: bytes) -> tuple[int, list[str]]:
    """``(rcode, addresses)`` of a DNS answer; ``ValueError`` for garbage."""
    try:
        _ident, flags, questions, answers, _ns, _extra = struct.unpack("!HHHHHH", payload[:12])
        offset = 12
        for _ in range(questions):
            offset = _skip_name(payload, offset) + 4
        addresses: list[str] = []
        for _ in range(answers):
            offset = _skip_name(payload, offset)
            rtype, _rclass, _ttl, rdlength = struct.unpack("!HHIH", payload[offset:offset + 10])
            offset += 10
            rdata = payload[offset:offset + rdlength]
            offset += rdlength
            if len(rdata) != rdlength:
                raise ValueError("truncated record")
            if (rtype == _TYPE_A and rdlength == 4) or (rtype == _TYPE_AAAA and rdlength == 16):
                addresses.append(str(ipaddress.ip_address(rdata)))
    except (IndexError, struct.error) as exc:
        raise ValueError("malformed DNS response") from exc
    return flags & 0x000F, addresses


def usable_address(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    if ip.is_unspecified or ip.is_multicast or ip.is_loopback:
        return False
    # sing-box fake-ip pool: a TUN answer, never the real server.
    return not (ip.version == 4 and ip in ipaddress.ip_network("198.18.0.0/15"))


def _doh_lookup(server: str, host: str, timeout: float) -> set[str]:
    """A and AAAA over one TLS connection to one resolver."""
    connection = http.client.HTTPSConnection(server, 443, timeout=timeout, context=get_ssl_context())
    try:
        found: set[str] = set()
        name_missing = False
        for qtype in (_TYPE_A, _TYPE_AAAA):
            connection.request(
                "POST",
                DOH_PATH,
                body=build_query(host, qtype),
                headers={"Content-Type": "application/dns-message", "Accept": "application/dns-message"},
            )
            response = connection.getresponse()
            body = response.read(65535)
            if response.status != 200:
                raise BootstrapDnsError(f"DoH {server}: HTTP {response.status}")
            rcode, addresses = parse_response(body)
            if rcode == _RCODE_NXDOMAIN:
                name_missing = True
                break
            if rcode != 0:
                raise BootstrapDnsError(f"DoH {server}: rcode {rcode}")
            found.update(address for address in addresses if usable_address(address))
        if name_missing and not found:
            raise BootstrapNameNotFound(host)
        return found
    finally:
        connection.close()


def resolve_doh(
    host: str,
    *,
    timeout: float = 3.0,
    servers: Iterable[str] = DOH_SERVERS,
    lookup: Callable[[str, str, float], set[str]] = _doh_lookup,
) -> set[str]:
    """First non-empty answer of any resolver; all of them are asked at once."""
    targets = tuple(servers)
    executor = ThreadPoolExecutor(max_workers=max(1, len(targets)), thread_name_prefix="bootstrap-doh")
    try:
        futures = [executor.submit(lookup, server, host, timeout) for server in targets]
        missing = 0
        last_error: Exception | None = None
        try:
            for future in as_completed(futures, timeout=timeout + 1.0):
                try:
                    addresses = future.result()
                except BootstrapNameNotFound as exc:
                    missing += 1
                    last_error = exc
                    continue
                except Exception as exc:  # noqa: BLE001 - network, TLS, garbage: try the next one
                    last_error = exc
                    continue
                if addresses:
                    return addresses
        except TimeoutError as exc:
            last_error = last_error or exc
        if missing and missing == len(targets):
            raise BootstrapNameNotFound(host)
        raise BootstrapDnsError(f"no trusted resolver answered: {last_error}")
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


class BootstrapCache:
    """Last server addresses obtained over the trusted path."""

    def __init__(self, path: Path, *, clock: Callable[[], float] = time.time) -> None:
        self._path = Path(path)
        self._clock = clock
        self._lock = threading.Lock()

    def _load(self) -> dict[str, dict]:
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        entries = payload.get("hosts") if isinstance(payload, dict) else None
        return entries if isinstance(entries, dict) else {}

    def _fresh(self, entry: object, now: float) -> bool:
        if not isinstance(entry, dict):
            return False
        try:
            age = now - float(entry.get("saved_at", 0) or 0)
        except (TypeError, ValueError):
            return False
        return 0 <= age <= CACHE_MAX_AGE_SEC

    def lookup(self, host: str) -> list[str]:
        host = normalize_host(host)
        with self._lock:
            entry = self._load().get(host)
        if not self._fresh(entry, self._clock()):
            return []
        result: list[str] = []
        for raw in entry.get("addresses") or []:  # type: ignore[union-attr]
            address = str(raw)
            if usable_address(address):
                address = str(ipaddress.ip_address(address))
                if address not in result:
                    result.append(address)
        return result

    def remember(self, host: str, addresses: Iterable[str]) -> None:
        host = normalize_host(host)
        cleaned = sorted({str(ipaddress.ip_address(a)) for a in addresses}, key=lambda a: (":" in a, a))
        if not host or not cleaned:
            return
        with self._lock:
            now = self._clock()
            entries = {name: entry for name, entry in self._load().items() if self._fresh(entry, now)}
            if entries.get(host, {}).get("addresses") == cleaned and now - float(entries[host]["saved_at"]) < 3600:
                return
            entries[host] = {"addresses": cleaned, "saved_at": now}
            temporary = self._path.with_suffix(self._path.suffix + ".tmp")
            try:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                temporary.write_text(json.dumps({"version": 1, "hosts": entries}, indent=2), encoding="utf-8")
                os.replace(temporary, self._path)
            except OSError:
                pass  # the cache is a safety net only


_cache: BootstrapCache | None = None


def configure_cache(path: Path | None) -> None:
    """Enable the persistent last-known-good cache (app) or disable it (tests)."""
    global _cache
    _cache = BootstrapCache(path) if path is not None else None


def _system_lookup(host: str) -> set[str]:
    resolved: set[str] = set()
    for info in socket.getaddrinfo(host, None, 0, socket.SOCK_STREAM):
        address = str(info[4][0]).split("%", 1)[0] if info and info[4] else ""
        if usable_address(address):
            resolved.add(str(ipaddress.ip_address(address)))
    return resolved


def resolve_bootstrap(
    host: str,
    *,
    timeout: float = 3.0,
    doh: Callable[[str], set[str]] | None = None,
    system: Callable[[str], set[str]] = _system_lookup,
) -> BootstrapResolution:
    """Server addresses: trusted DoH -> system resolver -> remembered address.

    Blocking, worker threads only. Raises ``OSError`` when none of the three
    sources knows the name.
    """
    host = normalize_host(host)
    if not host:
        return BootstrapResolution(frozenset(), "literal")
    try:
        return BootstrapResolution(frozenset({str(ipaddress.ip_address(host))}), "literal")
    except ValueError:
        pass
    lookup = doh or (lambda name: resolve_doh(name, timeout=timeout))
    trusted_error: Exception | None = None
    try:
        addresses = {a for a in lookup(host) if usable_address(a)}
    except BootstrapNameNotFound:
        raise  # trusted resolvers deny the name: neither ISP answers nor old cache are trustworthy
    except Exception as exc:  # noqa: BLE001
        trusted_error = exc
        addresses = set()
    if addresses:
        if _cache is not None:
            _cache.remember(host, addresses)
        return BootstrapResolution(frozenset(addresses), "doh")
    system_error: Exception | None = None
    try:
        addresses = {a for a in system(host) if usable_address(a)}
    except (OSError, UnicodeError) as exc:
        system_error = exc if isinstance(exc, OSError) else OSError(str(exc))
        addresses = set()
    if addresses:
        return BootstrapResolution(frozenset(addresses), "system")
    cached = _cache.lookup(host) if _cache is not None else []
    if cached:
        return BootstrapResolution(frozenset(cached), "cache")
    raise system_error or BootstrapDnsError(f"server name not resolved: {trusted_error}")
