"""Free Cloudflare WARP profiles in one click (AmneziaWG + MASQUE).

Mirrors the defaults of https://warp-generation.github.io/: a public helper
registers a fresh WARP device and returns its keys; Lumen turns them into
ready-to-use nodes (three AmneziaWG masks and MASQUE over HTTP/3 and HTTP/2).
Network access is injected (``open_url``) so the builders stay testable and
the caller decides whether to go through the active proxy or directly.
"""

from __future__ import annotations

import json
import random
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any
from urllib.request import Request

from PyQt6.QtCore import QThread, pyqtSignal

from .constants import APP_VERSION
from .link_parser import LinkParseError, _parse_clash_proxy_payload, _parse_wireguard_config
from .models import Node

WARP_GROUP = "WARP"

# Public registration helpers used by warp-generation.github.io, tried in order.
AWG_DATA_ENDPOINTS: tuple[str, ...] = (
    "https://www.warp-generator.workers.dev",
    "https://warp-gen.netlify.app/",
    "https://warp.sub-aggregator.workers.dev",
    "https://warp-vercel-chi.vercel.app/api/warp-data",
    "https://warp-vercel-murex.vercel.app/api/warp-data",
)
MASQUE_DATA_ENDPOINTS: tuple[str, ...] = (
    "https://www.masque-generator.workers.dev/",
    "https://masque-generator.vercel.app/api/warp-data",
)

WARP_ENDPOINT_PREFIXES: tuple[str, ...] = (
    "162.159.192.", "162.159.195.", "engage.cloudflareclient.com",
    "8.6.112.", "8.34.70.", "8.34.146.", "8.35.211.", "8.39.125.", "8.39.204.",
    "8.39.214.", "8.47.69.", "188.114.96.", "188.114.97.", "188.114.98.", "188.114.99.",
)
WARP_ENDPOINT_PORTS: tuple[int, ...] = (
    500, 854, 859, 864, 878, 880, 890, 891, 894, 903, 908, 928, 934, 939, 942, 943,
    945, 946, 955, 968, 987, 988, 1002, 1010, 1014, 1018, 1070, 1074, 1180, 1387,
    1701, 1843, 2371, 2408, 2506, 3138, 3476, 3581, 3854, 4177, 4198, 4233, 4500,
    5279, 5956, 7103, 7152, 7156, 7281, 7559, 8319, 8742, 8854, 8886,
)
MASQUE_SERVER = "162.159.198.2"
MASQUE_PORT = 443
MASQUE_SNI = "4pda.to"
WARP_DNS = ("1.1.1.1", "1.0.0.1")
MASQUE_DNS = ("1.1.1.1", "1.0.0.1", "2606:4700:4700::1111", "2606:4700:4700::1001")
WARP_MTU = 1280
REQUEST_TIMEOUT = 8.0
MAX_RESPONSE_BYTES = 64 * 1024

# Obfuscation packets (AmneziaWG I1/I2) used by the generator's three
# "standard" profiles: QUIC Initial, a short QUIC packet and a SIP exchange.
_QUIC_MASK_HEX = (
    "ce000000010897a297ecc34cd6dd000044d0ec2e2e1ea2991f467ace4222129b5a098823784694b4897b9986"
    "ae0b7280135fa85e196d9ad980b150122129ce2a9379531b0fd3e871ca5fdb883c369832f730e272d7b8b74f"
    "393f9f0fa43f11e510ecb2219a52984410c204cf875585340c62238e14ad04dff382f2c200e0ee22fe743b9c"
    "6b8b043121c5710ec289f471c91ee414fca8b8be8419ae8ce7ffc53837f6ade262891895f3f4cecd31bc93ac"
    "5599e18e4f01b472362b8056c3172b513051f8322d1062997ef4a383b01706598d08d48c221d30e74c7ce000"
    "cdad36b706b1bf9b0607c32ec4b3203a4ee21ab64df336212b9758280803fcab14933b0e7ee1e04a7becce3e"
    "2633f4852585c567894a5f9efe9706a151b615856647e8b7dba69ab357b3982f554549bef9256111b2d67afd"
    "e0b496f16962d4957ff654232aa9e845b61463908309cfd9de0a6abf5f425f577d7e5f6440652aa8da5f7358"
    "8e82e9470f3b21b27b28c649506ae1a7f5f15b876f56abc4615f49911549b9bb39dd804fde182bd2dcec0c33"
    "bad9b138ca07d4a4a1650a2c2686acea05727e2a78962a840ae428f55627516e73c83dd8893b02358e81b524"
    "b4d99fda6df52b3a8d7a5291326e7ac9d773c5b43b8444554ef5aea104a738ed650aa979674bbed38da58ac2"
    "9d87c29d387d80b526065baeb073ce65f075ccb56e47533aef357dceaa8293a523c5f6f790be90e4731123d3"
    "c6152a70576e90b4ab5bc5ead01576c68ab633ff7d36dcde2a0b2c68897e1acfc4d6483aaaeb635dd63c96b2"
    "b6a7a2bfe042f6aed82e5363aa850aace12ee3b1a93f30d8ab9537df483152a5527faca21efc9981b304f11f"
    "c95336f5b9637b174c5a0659e2b22e159a9fed4b8e93047371175b1d6d9cc8ab745f3b2281537d1c75fb9451"
    "871864efa5d184c38c185fd203de206751b92620f7c369e031d2041e152040920ac2c5ab5340bfc9d0561176"
    "abf10a147287ea90758575ac6a9f5ac9f390d0d5b23ee12af583383d994e22c0cf42383834bcd3ada1b3825a"
    "0664d8f3fb678261d57601ddf94a8a68a7c273a18c08aa99c7ad8c6c42eab67718843597ec9930457359dfdf"
    "bce024afc2dcf9348579a57d8d3490b2fa99f278f1c37d87dad9b221acd575192ffae1784f8e60ec7cee4068"
    "b6b988f0433d96d6a1b1865f4e155e9fe020279f434f3bf1bd117b717b92f6cd1cc9bea7d45978bcc3f24bda"
    "631a36910110a6ec06da35f8966c9279d130347594f13e9e07514fa370754d1424c0a1545c5070ef9fb2acd1"
    "4233e8a50bfc5978b5bdf8bc1714731f798d21e2004117c61f2989dd44f0cf027b27d4019e81ed4b5c31db34"
    "7c4a3a4d85048d7093cf16753d7b0d15e078f5c7a5205dc2f87e330a1f716738dce1c6180e9d02869b5546f1"
    "c4d2748f8c90d9693cba4e0079297d22fd61402dea32ff0eb69ebd65a5d0b687d87e3a8b2c42b648aa723c7c"
    "7daf37abcc4bb85caea2ee8f55bec20e913b3324ab8f5c3304f820d42ad1b9f2ffc1a3af9927136b4419e1e5"
    "79ab4c2ae3c776d293d397d575df181e6cae0a4ada5d67ecea171cca3288d57c7bbdaee3befe745fb7d634f7"
    "0386d873b90c4d6c6596bb65af68f9e5121e67ebf0d89d3c909ceedfb32ce9575a7758ff080724e1ab5d5f43"
    "074ecb53a479af21ed03d7b6899c36631c0166f9d47e5e1d4528a5d3d3f744029c4b1c190cbfbad06f5f83f7"
    "ad0429fa9a2719c56ffe3783460e166de2d8"
)
_SHORT_MASK_HEX = (
    "c400000001015c000040570b2e25e1a2fb2e1d5cf2bfdaeb0ca79c3255f6384628e6e6c22adb43440db63fa1"
    "d26ad16120d9cbdbf0dc2f7a8eb3525561b193c6b6a0ef44e8d118c3b04a3ae880c081a9b9e9732131591578"
    "7938abd8b925506b830d"
)
_SIP_INVITE_HEX = (
    "494e56495445207369703a626f624062696c6f78692e636f6d205349502f322e300d0a5669613a205349502f"
    "322e302f55445020706333332e61746c616e74612e636f6d3b6272616e63683d7a39684734624b3737366173"
    "646864730d0a4d61782d466f7277617264733a2037300d0a546f3a20426f62203c7369703a626f624062696c"
    "6f78692e636f6d3e0d0a46726f6d3a20416c696365203c7369703a616c6963654061746c616e74612e636f6d"
    "3e3b7461673d313932383330313737340d0a43616c6c2d49443a206138346234633736653636373130407063"
    "33332e61746c616e74612e636f6d0d0a435365713a2033313431353920494e564954450d0a436f6e74616374"
    "3a203c7369703a616c69636540706333332e61746c616e74612e636f6d3e0d0a436f6e74656e742d54797065"
    "3a206170706c69636174696f6e2f7364700d0a436f6e74656e742d4c656e6774683a20300d0a0d0a"
)
_SIP_TRYING_HEX = (
    "5349502f322e302031303020547279696e670d0a5669613a205349502f322e302f55445020706333332e6174"
    "6c616e74612e636f6d3b6272616e63683d7a39684734624b3737366173646864730d0a546f3a20426f62203c"
    "7369703a626f624062696c6f78692e636f6d3e0d0a46726f6d3a20416c696365203c7369703a616c69636540"
    "61746c616e74612e636f6d3e3b7461673d313932383330313737340d0a43616c6c2d49443a20613834623463"
    "373665363637313040706333332e61746c616e74612e636f6d0d0a435365713a2033313431353920494e5649"
    "54450d0a436f6e74656e742d4c656e6774683a20300d0a0d0a"
)

AWG_PROFILES: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = (
    ("WARP AWG · QUIC", (("I1", _QUIC_MASK_HEX),)),
    ("WARP AWG · QUIC lite", (("I1", _SHORT_MASK_HEX),)),
    ("WARP AWG · SIP", (("I1", _SIP_INVITE_HEX), ("I2", _SIP_TRYING_HEX))),
)

OpenUrl = Callable[[Request, float], Any]


class WarpGenerationError(RuntimeError):
    """No helper returned a usable WARP registration."""


@dataclass
class WarpResult:
    nodes: list[Node] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _clean(value: Any) -> str:
    text = str(value or "").strip()
    return "" if any(ch.isspace() for ch in text) else text


def parse_registration(payload: Any) -> dict[str, str]:
    """Validate a helper response: ``{privKey, peer_pub, client_ipv4, client_ipv6}``."""
    if not isinstance(payload, dict):
        raise WarpGenerationError("unexpected response format")
    data = {
        "private_key": _clean(payload.get("privKey") or payload.get("private_key")),
        "public_key": _clean(payload.get("peer_pub") or payload.get("public_key")),
        "ipv4": _clean(payload.get("client_ipv4") or payload.get("ipv4")),
        "ipv6": _clean(payload.get("client_ipv6") or payload.get("ipv6")),
    }
    if not data["private_key"] or not data["public_key"] or not data["ipv4"]:
        raise WarpGenerationError("response has no keys or address")
    return data


def fetch_registration(
    open_url: OpenUrl,
    endpoints: Sequence[str],
    *,
    headers: dict[str, str] | None = None,
    timeout: float = REQUEST_TIMEOUT,
    cancelled: Callable[[], bool] | None = None,
) -> dict[str, str]:
    """Ask each helper in turn and return the first valid registration."""
    failures: list[str] = []
    for url in endpoints:
        if cancelled is not None and cancelled():
            raise WarpGenerationError("cancelled")
        request = Request(
            url,
            headers={
                "User-Agent": f"Lumen/{APP_VERSION}",
                "Accept": "application/json",
                **(headers or {}),
            },
        )
        try:
            with open_url(request, timeout) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise WarpGenerationError("response is too large")
            return parse_registration(json.loads(raw.decode("utf-8")))
        except Exception as exc:  # try the next helper
            host = url.split("//", 1)[-1].split("/", 1)[0]
            failures.append(f"{host}: {exc}")
    raise WarpGenerationError("; ".join(failures) or "no endpoints")


def random_endpoint(rng: random.Random | None = None) -> str:
    rng = rng or random.SystemRandom()
    port = rng.choice(WARP_ENDPOINT_PORTS)
    prefix = rng.choice(WARP_ENDPOINT_PREFIXES)
    if not prefix.endswith("."):
        return f"{prefix}:{port}"
    return f"{prefix}{rng.randint(1, 10)}:{port}"


def build_awg_config(
    registration: dict[str, str],
    masks: Sequence[tuple[str, str]],
    endpoint: str,
) -> str:
    """AmneziaWG .conf exactly like the generator's default download."""
    mask_lines = "".join(f"{key} = <b 0x{value}>\n" for key, value in masks)
    return (
        "[Interface]\n"
        f"PrivateKey = {registration['private_key']}\n"
        f"Address = {registration['ipv4']}\n"
        f"DNS = {', '.join(WARP_DNS)}\n"
        f"MTU = {WARP_MTU}\n"
        "S1 = 0\nS2 = 0\nS3 = 0\nS4 = 0\n"
        "Jc = 4\nJmin = 40\nJmax = 70\n"
        "H1 = 1\nH2 = 2\nH3 = 3\nH4 = 4\n"
        f"{mask_lines}"
        "\n[Peer]\n"
        f"PublicKey = {registration['public_key']}\n"
        "AllowedIPs = 0.0.0.0/0, ::/0\n"
        f"Endpoint = {endpoint}\n"
    )


def build_masque_payloads(registration: dict[str, str]) -> list[dict[str, Any]]:
    """Clash/mihomo MASQUE proxies (HTTP/3 and HTTP/2) for one registration."""
    common: dict[str, Any] = {
        "type": "masque",
        "server": MASQUE_SERVER,
        "port": MASQUE_PORT,
        "sni": MASQUE_SNI,
        "private-key": registration["private_key"],
        "public-key": registration["public_key"],
        "ip": registration["ipv4"],
        "mtu": WARP_MTU,
        "udp": True,
        "remote-dns-resolve": True,
        "dns": list(MASQUE_DNS),
    }
    if registration.get("ipv6"):
        common["ipv6"] = registration["ipv6"]
    return [
        {"name": "WARP MASQUE", **common},
        {"name": "WARP MASQUE · HTTP/2", **common, "network": "h2"},
    ]


def _finish(node: Node, name: str) -> Node:
    node.name = name
    node.group = WARP_GROUP
    if WARP_GROUP not in node.tags:
        node.tags = [*node.tags, WARP_GROUP]
    return node


def build_awg_nodes(registration: dict[str, str], rng: random.Random | None = None) -> list[Node]:
    nodes: list[Node] = []
    for name, masks in AWG_PROFILES:
        config = build_awg_config(registration, masks, random_endpoint(rng))
        nodes.append(_finish(_parse_wireguard_config(config), name))
    return nodes


def build_masque_nodes(registration: dict[str, str]) -> list[Node]:
    return [
        _finish(_parse_clash_proxy_payload(payload), payload["name"])
        for payload in build_masque_payloads(registration)
    ]


def generate_warp_nodes(
    open_url: OpenUrl,
    *,
    rng: random.Random | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> WarpResult:
    """Fetch AWG and MASQUE registrations; succeed when at least one works."""
    result = WarpResult()
    for label, endpoints, headers, builder in (
        ("AmneziaWG", AWG_DATA_ENDPOINTS, {"X-Client": "WARP"}, lambda reg: build_awg_nodes(reg, rng)),
        ("MASQUE", MASQUE_DATA_ENDPOINTS, None, build_masque_nodes),
    ):
        try:
            registration = fetch_registration(
                open_url, endpoints, headers=headers, cancelled=cancelled
            )
            result.nodes.extend(builder(registration))
        except (WarpGenerationError, LinkParseError, ValueError) as exc:
            result.errors.append(f"{label}: {exc}")
    if not result.nodes:
        raise WarpGenerationError("; ".join(result.errors) or "no WARP profiles")
    return result


class WarpGenerationWorker(QThread):
    """Background registration so the welcome flow never blocks the UI."""

    done = pyqtSignal(object, str)  # WarpResult | None, error text

    def __init__(self, open_url: OpenUrl) -> None:
        super().__init__()
        self._open_url = open_url
        self._cancelled = threading.Event()
        self.setObjectName("lumen-warp-generator")

    def cancel(self) -> None:
        self._cancelled.set()

    def run(self) -> None:
        try:
            result = generate_warp_nodes(self._open_url, cancelled=self._cancelled.is_set)
        except Exception as exc:
            if not self._cancelled.is_set():
                self.done.emit(None, str(exc))
            return
        if not self._cancelled.is_set():
            self.done.emit(result, "")
