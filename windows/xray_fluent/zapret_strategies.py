"""winws2 strategies dedicated to the traffic of a VPN server.

A server strategy is only the desync part of one winws2 profile
(``--lua-desync`` / ``--payload`` / ``--out-range`` / ``--in-range``); the
target (server IP, transport, port) is added by :mod:`.zapret_server_scope`.
Strategies come from the winws2 catalogs ported from ZapretKVN
(``zapret/strategy_catalogs/winws2/<transport>.txt`` plus local
``<transport>.local.txt`` overrides). Each bound server picks one from the
catalog of its kind (TCP servers, QUIC servers, WireGuard); without a choice
the default strategy of the kind is used.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path
from types import MappingProxyType
from typing import Any, Iterable, Mapping

from .constants import BASE_DIR

log = logging.getLogger(__name__)

ZAPRET_DIR = BASE_DIR / "zapret"
CATALOG_DIR = ZAPRET_DIR / "strategy_catalogs" / "winws2"
_BIN_DIR = ZAPRET_DIR / "bin"
_LUA_DIR = ZAPRET_DIR / "lua"

SERVER_KINDS: tuple[str, ...] = ("tcp", "quic", "wireguard")
KIND_TRANSPORT: dict[str, str] = {"tcp": "tcp", "quic": "udp", "wireguard": "udp"}
KIND_TITLES: dict[str, str] = {"tcp": "TCP", "quic": "QUIC", "wireguard": "WireGuard"}
DEFAULT_STRATEGIES: dict[str, str] = {"tcp": "alt9", "quic": "general_bf_32", "wireguard": "general_bf_32"}

#: Catalog labels, from most to least battle-tested.
STRATEGY_LABELS: tuple[str, ...] = ("recommended", "stable", "stock", "game", "experimental", "caution")

_WIREGUARD_PROTOCOLS = frozenset({"wireguard", "wg", "warp", "awg", "amneziawg"})
_QUIC_PROTOCOLS = frozenset({"hysteria", "hysteria2", "hy2", "tuic"})
_UDP_NETWORKS = frozenset({"kcp", "mkcp", "quic"})

#: Arguments a strategy may hold; everything else belongs to the app.
STRATEGY_ARGUMENTS = ("--lua-desync=", "--payload=", "--out-range=", "--in-range=")
CORE_LUA_INITS: tuple[str, ...] = ("--lua-init=@lua/zapret-lib.lua", "--lua-init=@lua/zapret-antidpi.lua")

#: Blob name -> ``--blob=`` source (``@bin/<file>`` or an inline hex literal).
BLOB_REGISTRY: dict[str, str] = {
    "discord_active": "@bin/ACTIVE_DISCORD_UDP.bin",
    "dtls_w3": "@bin/dtls_clienthello_w3_org.bin",
    "fake_dbankcloud": "@bin/quic_initial_dbankcloud_ru.bin",
    "fake_http_max": "@bin/tls_clienthello_max_ru.bin",
    "fake_quic": "@bin/fake_quic.bin",
    "fake_quic_1": "@bin/fake_quic_1.bin",
    "fake_quic_2": "@bin/fake_quic_2.bin",
    "fake_quic_3": "@bin/fake_quic_3.bin",
    "fake_stun": "@bin/stun.bin",
    "fake_stun_as_tls": "@bin/stun.bin",
    "fake_tls": "@bin/fake_tls_1.bin",
    "fake_tls_1": "@bin/fake_tls_1.bin",
    "fake_tls_2": "@bin/fake_tls_2.bin",
    "fake_tls_3": "@bin/fake_tls_3.bin",
    "fake_tls_4": "@bin/fake_tls_4.bin",
    "fake_tls_5": "@bin/fake_tls_5.bin",
    "fake_tls_6": "@bin/fake_tls_6.bin",
    "fake_tls_7": "@bin/fake_tls_7.bin",
    "fake_tls_8": "@bin/fake_tls_8.bin",
    "game_active": "@bin/ACTIVE_GAME_UDP.bin",
    "http_max": "@bin/tls_clienthello_max_ru.bin",
    "http_req": "@bin/http_iana_org.bin",
    "quic1": "@bin/quic_1.bin",
    "quic2": "@bin/quic_2.bin",
    "quic3": "@bin/quic_3.bin",
    "quic4": "@bin/quic_4.bin",
    "quic5": "@bin/quic_5.bin",
    "quic6": "@bin/quic_6.bin",
    "quic7": "@bin/quic_7.bin",
    "quic_4pda": "@bin/quic_initial_4pda.to.bin",
    "quic_google": "@bin/quic_initial_www_google_com.bin",
    "quic_test": "@bin/quic_test_00.bin",
    "quic_vk": "@bin/quic_initial_vk_com.bin",
    "stun2": "@bin/stun2.bin",
    "stun_pat": "@bin/stun.bin",
    "syn_packet": "@bin/syn_packet.bin",
    "syndata3": "@bin/tls_clienthello_3.bin",
    "tls1": "@bin/tls_clienthello_1.bin",
    "tls10": "@bin/tls_clienthello_10.bin",
    "tls11": "@bin/tls_clienthello_11.bin",
    "tls12": "@bin/tls_clienthello_12.bin",
    "tls13": "@bin/tls_clienthello_13.bin",
    "tls14": "@bin/tls_clienthello_14.bin",
    "tls17": "@bin/tls_clienthello_17.bin",
    "tls18": "@bin/tls_clienthello_18.bin",
    "tls2": "@bin/tls_clienthello_2.bin",
    "tls2n": "@bin/tls_clienthello_2n.bin",
    "tls3": "@bin/tls_clienthello_3.bin",
    "tls4": "@bin/tls_clienthello_4.bin",
    "tls5": "@bin/tls_clienthello_5.bin",
    "tls6": "@bin/tls_clienthello_6.bin",
    "tls7": "@bin/tls_clienthello_7.bin",
    "tls8": "@bin/tls_clienthello_8.bin",
    "tls9": "@bin/tls_clienthello_9.bin",
    "tls_4pda": "@bin/tls_clienthello_4pda_to.bin",
    "tls_deepseek": "@bin/tls_clienthello_chat_deepseek_com.bin",
    "tls_google": "@bin/tls_clienthello_www_google_com.bin",
    "tls_gosuslugi": "@bin/tls_clienthello_gosuslugi_ru.bin",
    "tls_iana": "@bin/tls_clienthello_iana_org.bin",
    "tls_max": "@bin/tls_clienthello_max_ru.bin",
    "tls_sber": "@bin/tls_clienthello_sberbank_ru.bin",
    "tls_sber_v2": "@bin/tls_clienthello_sberbank_ru_v2.bin",
    "tls_sochi": "@bin/tls_clienthello_sochi_park.bin",
    "tls_stun": "@bin/stun.bin",
    "tls_vk": "@bin/tls_clienthello_vk_com.bin",
    "tls_vk_kyber": "@bin/tls_clienthello_vk_com_kyber.bin",
    "zero256": "@bin/zero_256.bin",
    "fake_default_udp": "0x00000000000000000000000000000000",
    "hex_00": "0x00",
    "hex_0e0e0f0e": "0x0E0E0F0E",
    "hex_0f0e0e0f": "0x0F0E0E0F",
    "hex_0f0f0f0f": "0x0F0F0F0F",
    "tls_zero4": "0x00000000",
    "zero64": "0x" + "00" * 64,
}

#: Provided by winws2 itself; declaring them breaks the start.
BUILTIN_BLOBS = frozenset({"fake_default_tls", "fake_default_quic", "fake_default_http", "fake_unknown_256", "fake_zero64"})

#: desync function -> lua file defining it (functions outside the core lua).
LUA_EXTENSION_FUNCS: dict[str, str] = {
    "discord_ecn_exploit": "custom_funcs.lua",
    "discord_router_alert": "custom_funcs.lua",
    "discord_timestamp_travel": "custom_funcs.lua",
    "discord_ultimate_combo": "custom_funcs.lua",
    "discord_urgent_sni": "custom_funcs.lua",
    "discord_window_collapse": "custom_funcs.lua",
    "fakemultidisorder": "fakemultidisorder.lua",
    "fakemultisplit": "fakemultisplit.lua",
    "hostfakesplit_multi": "zapret-multishake.lua",
    "multisplit_tls": "custom_funcs.lua",
    "tls_aggressive": "custom_funcs.lua",
    "tls_disorder_gentle": "custom_funcs.lua",
    "tls_fake_disorder_gentle": "custom_funcs.lua",
    "tls_fake_flood": "custom_funcs.lua",
    "tls_fake_simple": "custom_funcs.lua",
    "tls_fake_split": "custom_funcs.lua",
    "tls_multisplit_sni": "custom_funcs.lua",
    "tls_split_gentle": "custom_funcs.lua",
}

_BLOB_REFERENCE_RE = re.compile(r"(?:blob|pattern)=([A-Za-z0-9_]+)")
_DESYNC_FUNC_RE = re.compile(r"--lua-desync=([a-z0-9_]+)", re.IGNORECASE)


@dataclass(frozen=True)
class Strategy:
    strategy_id: str
    transport: str
    name: str
    args: tuple[str, ...]
    description: str = ""
    author: str = ""
    label: str = ""

    @property
    def is_pass(self) -> bool:
        return all(arg.split(":", 1)[0] == "--lua-desync=pass" for arg in self.args if arg.startswith("--lua-desync="))


def blob_names_in_args(args: Iterable[str]) -> tuple[str, ...]:
    """Blob names referenced by the arguments (builtins and hex literals excluded)."""
    found: dict[str, None] = {}
    for argument in args:
        for name in _BLOB_REFERENCE_RE.findall(str(argument)):
            if not name.lower().startswith("0x") and name not in BUILTIN_BLOBS:
                found.setdefault(name, None)
    return tuple(found)


def unresolved_blob_names(args: Iterable[str]) -> tuple[str, ...]:
    return tuple(name for name in blob_names_in_args(args) if name not in BLOB_REGISTRY)


def lua_init_arguments(args: Iterable[str]) -> tuple[str, ...]:
    """Extension ``--lua-init`` options needed by the desync functions in ``args``."""
    seen: dict[str, None] = {}
    for argument in args:
        for func in _DESYNC_FUNC_RE.findall(str(argument)):
            lua_file = LUA_EXTENSION_FUNCS.get(func.lower())
            if lua_file:
                seen.setdefault(f"--lua-init=@lua/{lua_file}", None)
    return tuple(seen)


def strategy_global_args(args: Iterable[str]) -> tuple[str, ...]:
    """Process-wide options a strategy needs: core + extension lua, blob definitions."""
    items = tuple(args)
    result = list(CORE_LUA_INITS)
    result.extend(init for init in lua_init_arguments(items) if init not in result)
    for name in blob_names_in_args(items):
        source = BLOB_REGISTRY.get(name)
        if source:
            result.append(f"--blob={name}:{source}")
    return tuple(result)


def parse_strategy_lines(text: str) -> tuple[str, ...]:
    """Validated strategy lines; ``ValueError`` for anything outside a profile body."""
    args: list[str] = []
    for raw in str(text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        prefix = next((item for item in STRATEGY_ARGUMENTS if line.startswith(item)), "")
        if not prefix or not line[len(prefix):].strip() or any(char.isspace() for char in line):
            raise ValueError("only --lua-desync=, --payload=, --out-range=, --in-range= lines are allowed")
        args.append(line)
    if not any(arg.startswith("--lua-desync=") for arg in args):
        raise ValueError("no --lua-desync line")
    return tuple(args)


def clean_strategy_name(name: str) -> str:
    """Catalog title without emoji and pictographs."""
    kept = "".join(
        char
        for char in str(name or "")
        if unicodedata.category(char) not in ("So", "Sk", "Cs", "Co", "Cf")
        and not 0xFE00 <= ord(char) <= 0xFE0F
    )
    return re.sub(r"\s+", " ", kept).strip(" -\u2014\u00b7")


def _parse_catalog(path: Path, transport: str) -> dict[str, Strategy]:
    """``[id]`` sections of ``key = value`` metadata followed by winws2 lines."""
    if not path.is_file():
        return {}
    sections: list[tuple[str, dict[str, str], list[str]]] = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            sections.append((line[1:-1].strip(), {}, []))
        elif not sections:
            continue
        elif line.startswith("--"):
            sections[-1][2].append(line)
        elif "=" in line:
            key, value = line.split("=", 1)
            sections[-1][1][key.strip().lower()] = value.strip()
    result: dict[str, Strategy] = {}
    rejected = 0
    for strategy_id, meta, lines in sections:
        if not strategy_id or not lines:
            continue
        try:
            args = parse_strategy_lines("\n".join(lines))
        except ValueError:
            rejected += 1
            continue
        if unresolved_blob_names(args):
            rejected += 1
            continue
        result[strategy_id] = Strategy(
            strategy_id=strategy_id,
            transport=transport,
            name=clean_strategy_name(meta.get("name", "")) or strategy_id,
            args=args,
            description=meta.get("description", ""),
            author=meta.get("author", ""),
            label=meta.get("label", "").strip().lower(),
        )
    if rejected:
        log.warning("zapret catalog %s: skipped %d entries", path.name, rejected)
    return result


_CATALOG_CACHE: dict[str, tuple[tuple, Mapping[str, Strategy]]] = {}


def load_catalog(transport: str, catalog_dir: Path | None = None) -> Mapping[str, Strategy]:
    """Upstream catalog merged with local overrides; cached on file mtime/size."""
    root = Path(catalog_dir) if catalog_dir is not None else CATALOG_DIR
    paths = (root / f"{transport}.txt", root / f"{transport}.local.txt")
    signature: list[tuple[str, int, int]] = [(str(root), 0, 0)]
    for path in paths:
        try:
            stat = path.stat()
        except OSError:
            continue
        signature.append((path.name, stat.st_mtime_ns, stat.st_size))
    key = f"{root}|{transport}"
    cached = _CATALOG_CACHE.get(key)
    if cached is not None and cached[0] == tuple(signature):
        return cached[1]
    merged: dict[str, Strategy] = {}
    for path in paths:
        merged.update(_parse_catalog(path, transport))
    names = Counter(entry.name.casefold() for entry in merged.values())
    for strategy_id, entry in merged.items():
        if names[entry.name.casefold()] > 1:
            merged[strategy_id] = replace(entry, name=f"{entry.name} ({strategy_id})")
    catalog = MappingProxyType(merged)
    _CATALOG_CACHE[key] = (tuple(signature), catalog)
    return catalog


def kind_catalog(kind: str, catalog_dir: Path | None = None) -> Mapping[str, Strategy]:
    return load_catalog(KIND_TRANSPORT.get(kind, "tcp"), catalog_dir)


#: Binding value of a server that uses a catalog strategy: ``@server`` (the
#: default strategy of its kind) or ``@server:<strategy id>``.
SERVER_STRATEGY_PRESET = "@server"


def is_server_strategy(preset: Any) -> bool:
    value = str(preset or "").strip()
    return value == SERVER_STRATEGY_PRESET or value.startswith(SERVER_STRATEGY_PRESET + ":")


def server_strategy_id(preset: Any) -> str:
    """Strategy id stored in a ``@server:<id>`` binding ("" for the default)."""
    value = str(preset or "").strip()
    if not value.startswith(SERVER_STRATEGY_PRESET + ":"):
        return ""
    return value[len(SERVER_STRATEGY_PRESET) + 1:].strip()


def server_strategy_preset(strategy_id: str = "") -> str:
    sid = str(strategy_id or "").strip()
    return f"{SERVER_STRATEGY_PRESET}:{sid}" if sid else SERVER_STRATEGY_PRESET


def strategy_for(kind: str, strategy_id: str = "", catalog_dir: Path | None = None) -> Strategy | None:
    """Chosen strategy of a server kind; the default one when none (or a vanished one) is chosen."""
    catalog = kind_catalog(kind, catalog_dir)
    entry = catalog.get(str(strategy_id or "").strip())
    if entry is None:
        entry = catalog.get(DEFAULT_STRATEGIES.get(kind, ""))
    return entry


def strategy_sort_key(strategy: Strategy) -> tuple[int, str]:
    try:
        rank = STRATEGY_LABELS.index(strategy.label)
    except ValueError:
        rank = len(STRATEGY_LABELS)
    return rank, strategy.name.casefold()


def node_server_kind(node: Any) -> str:
    """``tcp`` / ``quic`` / ``wireguard``: which strategy family fits the node."""
    outbound = getattr(node, "outbound", None) or {}
    protocol = ""
    network = ""
    if isinstance(outbound, dict):
        protocol = str(outbound.get("protocol") or outbound.get("type") or "").strip().lower()
        stream = outbound.get("streamSettings")
        if isinstance(stream, dict):
            network = str(stream.get("network") or "").strip().lower()
    protocol = protocol or str(getattr(node, "scheme", "") or "").strip().lower()
    if protocol in _WIREGUARD_PROTOCOLS:
        return "wireguard"
    if protocol in _QUIC_PROTOCOLS or network in _UDP_NETWORKS:
        return "quic"
    return "tcp"


def missing_blob_files() -> tuple[str, ...]:
    """Registry entries whose ``@bin`` file is not shipped."""
    return tuple(
        name
        for name, source in sorted(BLOB_REGISTRY.items())
        if source.startswith("@bin/") and not (_BIN_DIR / source[len("@bin/"):]).is_file()
    )
