"""Proxy chain (v2rayN-style "previous proxy" / "landing proxy").

Traffic path when the chain is enabled::

    app -> front proxy -> selected (main) server -> exit proxy -> target site

Both hops are optional: only a front hop, only an exit hop or both can be set.
The chain is expressed purely through outbound dialing:

* Xray: ``streamSettings.sockopt.dialerProxy``
* sing-box: dial field ``detour``

The module is intentionally free of Qt so it can be unit-tested in isolation.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Iterable

CHAIN_FRONT_TAG = "chain-front"
CHAIN_MAIN_TAG = "chain-main"

_FULL_CONFIG_PROTOCOLS = frozenset({"xray_config", "singbox_config"})


class ProxyChainError(ValueError):
    """Raised when the configured chain cannot be built for the selected server."""


@dataclass
class ProxyChain:
    front: Any | None = None
    exit: Any | None = None
    # Human-readable warnings about skipped hops (v2rayN parity: a missing or
    # unsupported hop is skipped with a warning instead of failing the start).
    notes: list[str] = field(default_factory=list)

    @property
    def active(self) -> bool:
        return self.front is not None or self.exit is not None

    @property
    def hops(self) -> tuple[Any, ...]:
        return tuple(node for node in (self.front, self.exit) if node is not None)

    def describe(self, main: Any | None = None) -> str:
        parts: list[str] = []
        if self.front is not None:
            parts.append(_node_label(self.front))
        parts.append(_node_label(main) if main is not None else "сервер")
        if self.exit is not None:
            parts.append(_node_label(self.exit))
        return " → ".join(parts)


def _node_label(node: Any) -> str:
    name = str(getattr(node, "name", "") or "").strip()
    if name:
        return name
    server = str(getattr(node, "server", "") or "").strip()
    return server or str(getattr(node, "id", "") or "?")


def node_protocol(node: Any) -> str:
    outbound = getattr(node, "outbound", None)
    if not isinstance(outbound, dict):
        return ""
    return str(outbound.get("protocol") or "").strip().lower()


def is_full_config_node(node: Any) -> bool:
    return node_protocol(node) in _FULL_CONFIG_PROTOCOLS


# Protocols that only the native sing-box core can dial.  Kept in sync with
# ``application.node_runtime_service.is_native_singbox_only_node`` but local so
# this module stays importable without Qt.
_SINGBOX_ONLY_PROTOCOLS = frozenset(
    {
        "warp",
        "wireguard",
        "awg",
        "amneziawg",
        "hysteria",
        "hysteria2",
        "tuic",
        "mieru",
        "masque",
        "openvpn",
        "naive",
        "anytls",
        "singbox_config",
    }
)
_XRAY_STANDARD_PROTOCOLS = frozenset({"vless", "vmess", "trojan", "shadowsocks", "socks", "http"})


def is_xray_dialable_node(node: Any) -> bool:
    outbound = getattr(node, "outbound", None)
    if not isinstance(outbound, dict) or not outbound:
        return False
    protocol = node_protocol(node)
    if not protocol or protocol in _SINGBOX_ONLY_PROTOCOLS or protocol == "xray_config":
        return False
    if isinstance(outbound.get("singbox"), dict):
        return protocol in _XRAY_STANDARD_PROTOCOLS
    return True


def _setting(settings: Any, name: str, default: Any) -> Any:
    return getattr(settings, name, default) if settings is not None else default


def chain_node_ids(settings: Any) -> tuple[str, str]:
    if not bool(_setting(settings, "proxy_chain_enabled", False)):
        return "", ""
    front_id = str(_setting(settings, "proxy_chain_front_node_id", "") or "").strip()
    exit_id = str(_setting(settings, "proxy_chain_exit_node_id", "") or "").strip()
    return front_id, exit_id


def resolve_proxy_chain(settings: Any, nodes: Iterable[Any], main: Any | None) -> ProxyChain | None:
    """Return the hops configured in settings for the given main server.

    ``None`` means the chain is disabled (or no hop is configured).  Hops that
    cannot be used are skipped and explained in ``ProxyChain.notes``.
    """
    front_id, exit_id = chain_node_ids(settings)
    if not front_id and not exit_id:
        return None
    chain = ProxyChain()
    if main is not None and is_full_config_node(main):
        chain.notes.append(
            f"Цепочка прокси пропущена: сервер «{_node_label(main)}» — полный конфиг, его маршруты не меняются."
        )
        return chain
    by_id = {str(getattr(node, "id", "") or ""): node for node in nodes or ()}
    main_id = str(getattr(main, "id", "") or "") if main is not None else ""

    def pick(node_id: str, role: str) -> Any | None:
        if not node_id:
            return None
        node = by_id.get(node_id)
        if node is None:
            chain.notes.append(f"{role} прокси не найден (сервер удалён) — звено пропущено.")
            return None
        if node_id == main_id:
            chain.notes.append(f"{role} прокси совпадает с выбранным сервером — звено пропущено.")
            return None
        if is_full_config_node(node):
            chain.notes.append(
                f"{role} прокси «{_node_label(node)}» — полный конфиг и не может быть звеном цепочки — пропущено."
            )
            return None
        return node

    chain.front = pick(front_id, "Предыдущий")
    chain.exit = pick(exit_id, "Выходной")
    return chain


def proxy_chain_signature(settings: Any, nodes: Iterable[Any]) -> tuple[Any, ...]:
    """Stable value for runtime signatures: changes when a hop or its link changes."""
    front_id, exit_id = chain_node_ids(settings)
    if not front_id and not exit_id:
        return ()
    by_id = {str(getattr(node, "id", "") or ""): node for node in nodes or ()}

    def hop(node_id: str) -> tuple[str, str]:
        node = by_id.get(node_id) if node_id else None
        if node is None:
            return node_id, ""
        return node_id, str(getattr(node, "link", "") or "") or repr(getattr(node, "outbound", None))

    return hop(front_id), hop(exit_id)


def _xray_sockopt(outbound: dict[str, Any]) -> dict[str, Any]:
    stream = outbound.get("streamSettings")
    if not isinstance(stream, dict):
        stream = {}
        outbound["streamSettings"] = stream
    sockopt = stream.get("sockopt")
    if not isinstance(sockopt, dict):
        sockopt = {}
        stream["sockopt"] = sockopt
    return sockopt


def _xray_hop_outbound(chain: ProxyChain, node: Any, role: str) -> dict[str, Any] | None:
    if not is_xray_dialable_node(node):
        chain.notes.append(
            f"{role} прокси «{_node_label(node)}» ({node_protocol(node) or '?'}) не поддерживается ядром Xray — звено пропущено."
        )
        return None
    outbound = deepcopy(node.outbound)
    outbound.pop("singbox", None)
    return outbound


def apply_xray_proxy_chain(
    outbounds: list[Any],
    chain: ProxyChain | None,
    *,
    proxy_tag: str = "proxy",
) -> tuple[str, ...]:
    """Wire the chain into an Xray outbound list in place.

    The main server outbound must already be tagged ``proxy_tag``.  After the
    call routing rules that point to ``proxy_tag`` reach the exit hop (or the
    main server when there is no exit hop).  Returns the applied roles.
    """
    if chain is None or not chain.active or not isinstance(outbounds, list):
        return ()
    index = next(
        (i for i, item in enumerate(outbounds) if isinstance(item, dict) and item.get("tag") == proxy_tag),
        None,
    )
    if index is None:
        chain.notes.append("В конфиге нет outbound `proxy` — цепочка прокси не применена.")
        return ()
    main = outbounds[index]
    front = _xray_hop_outbound(chain, chain.front, "Предыдущий") if chain.front is not None else None
    exit_ = _xray_hop_outbound(chain, chain.exit, "Выходной") if chain.exit is not None else None
    applied: list[str] = []

    if front is not None:
        main_sockopt = _xray_sockopt(main)
        inherited = str(main_sockopt.get("dialerProxy") or "").strip()
        front["tag"] = CHAIN_FRONT_TAG
        front_sockopt = _xray_sockopt(front)
        if inherited:
            # e.g. the sing-box protect tunnel of the hybrid sidecar
            front_sockopt["dialerProxy"] = inherited
        else:
            front_sockopt.pop("dialerProxy", None)
        main_sockopt["dialerProxy"] = CHAIN_FRONT_TAG
        outbounds.insert(index + 1, front)
        applied.append("front")

    if exit_ is not None:
        main["tag"] = CHAIN_MAIN_TAG
        exit_["tag"] = proxy_tag
        _xray_sockopt(exit_)["dialerProxy"] = CHAIN_MAIN_TAG
        outbounds.insert(index, exit_)
        applied.append("exit")
    return tuple(applied)
