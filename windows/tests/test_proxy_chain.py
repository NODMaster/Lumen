"""Proxy chain: app -> front proxy -> selected server -> exit proxy -> site.

Pure config-building tests: nothing is started and no network is touched.
"""

from __future__ import annotations

import json
from pathlib import Path

from xray_fluent.engines.singbox.runtime_planner import parse_singbox_document, plan_singbox_runtime
from xray_fluent.models import AppSettings, Node, RoutingSettings
from xray_fluent.proxy_chain import (
    CHAIN_FRONT_TAG,
    CHAIN_MAIN_TAG,
    apply_xray_proxy_chain,
    proxy_chain_signature,
    resolve_proxy_chain,
)


def _vless(node_id: str, server: str) -> Node:
    return Node(
        id=node_id,
        name=node_id,
        scheme="vless",
        server=server,
        port=443,
        link=f"vless://{node_id}@{server}:443",
        outbound={
            "protocol": "vless",
            "settings": {
                "vnext": [
                    {
                        "address": server,
                        "port": 443,
                        "users": [{"id": "00000000-0000-0000-0000-000000000000", "encryption": "none"}],
                    }
                ]
            },
            "streamSettings": {"security": "tls"},
        },
    )


def _socks(node_id: str, server: str) -> Node:
    return Node(
        id=node_id,
        name=node_id,
        scheme="socks",
        server=server,
        port=1080,
        outbound={"protocol": "socks", "settings": {"servers": [{"address": server, "port": 1080}]}},
    )


def _hysteria2(node_id: str, server: str) -> Node:
    return Node(
        id=node_id,
        name=node_id,
        scheme="hysteria2",
        server=server,
        outbound={
            "protocol": "hysteria2",
            "singbox": {"type": "hysteria2", "server": server, "server_port": 443, "password": "p"},
        },
    )


def _settings(front: str = "", exit_: str = "", enabled: bool = True) -> AppSettings:
    return AppSettings(
        proxy_chain_enabled=enabled,
        proxy_chain_front_node_id=front,
        proxy_chain_exit_node_id=exit_,
    )


def _sockopt(outbound: dict) -> dict:
    return outbound.get("streamSettings", {}).get("sockopt", {})


def _base_singbox_config() -> dict:
    return {
        "inbounds": [{"type": "mixed", "tag": "socks-in", "listen": "127.0.0.1", "listen_port": 10808}],
        "outbounds": [
            {"type": "direct", "tag": "proxy"},
            {"type": "direct", "tag": "direct"},
            {"type": "block", "tag": "block"},
        ],
        "route": {"rules": [], "final": "proxy"},
        "dns": {
            "servers": [
                {"tag": "bootstrap-dns", "type": "udp", "server": "1.1.1.1"},
                {"tag": "proxy-dns", "type": "https", "server": "dns.google"},
            ],
            "final": "bootstrap-dns",
        },
    }


def _plan_singbox(main: Node, chain, **kwargs):
    document = parse_singbox_document(Path("test.json"), json.dumps(_base_singbox_config()))
    return plan_singbox_runtime(
        document,
        main,
        routing=RoutingSettings(mode="global"),
        tun_mode=False,
        proxy_chain=chain,
        **kwargs,
    )


def _all_dials(config: dict) -> dict[str, dict]:
    items = list(config.get("outbounds") or []) + list(config.get("endpoints") or [])
    return {str(item.get("tag")): item for item in items if isinstance(item, dict)}


# ---- resolution -----------------------------------------------------------

def test_chain_is_off_when_disabled_or_empty() -> None:
    main = _vless("main", "203.0.113.1")
    hop = _socks("hop", "198.51.100.1")
    assert resolve_proxy_chain(_settings("hop", enabled=False), [main, hop], main) is None
    assert resolve_proxy_chain(_settings(), [main, hop], main) is None
    assert proxy_chain_signature(_settings("hop", enabled=False), [main, hop]) == ()


def test_missing_or_self_hops_are_skipped_with_notes() -> None:
    main = _vless("main", "203.0.113.1")
    chain = resolve_proxy_chain(_settings("gone", "main"), [main], main)
    assert chain is not None and not chain.active
    assert len(chain.notes) == 2


def test_full_config_main_server_keeps_its_own_routes() -> None:
    main = Node(id="auto", name="AUTO", outbound={"protocol": "xray_config", "xray_config": {}})
    hop = _socks("hop", "198.51.100.1")
    chain = resolve_proxy_chain(_settings("hop"), [main, hop], main)
    assert chain is not None and not chain.active and chain.notes


def test_signature_changes_when_a_hop_changes() -> None:
    main = _vless("main", "203.0.113.1")
    hop = _vless("hop", "198.51.100.1")
    before = proxy_chain_signature(_settings("hop"), [main, hop])
    hop.link = "vless://other"
    assert proxy_chain_signature(_settings("hop"), [main, hop]) != before


def test_settings_round_trip() -> None:
    settings = _settings("a", "b")
    settings.zapret_server_presets = {"node-1": "general", "node-2": ""}
    restored = AppSettings.from_dict(settings.to_dict())
    assert restored.proxy_chain_enabled is True
    assert (restored.proxy_chain_front_node_id, restored.proxy_chain_exit_node_id) == ("a", "b")
    assert restored.zapret_server_presets == {"node-1": "general", "node-2": ""}
    assert AppSettings.from_dict({}).zapret_server_presets == {}


# ---- Xray ------------------------------------------------------------------

def test_xray_chain_wires_dialer_proxies_in_order() -> None:
    main = _vless("main", "203.0.113.1")
    front = _socks("front", "198.51.100.1")
    exit_ = _vless("exit", "192.0.2.1")
    chain = resolve_proxy_chain(_settings("front", "exit"), [main, front, exit_], main)
    main_outbound = dict(main.outbound, tag="proxy")
    outbounds = [main_outbound, {"tag": "direct", "protocol": "freedom"}]

    assert apply_xray_proxy_chain(outbounds, chain) == ("front", "exit")

    tags = [item["tag"] for item in outbounds]
    assert tags[0] == "proxy"  # routing rules / default outbound reach the exit hop
    by_tag = {item["tag"]: item for item in outbounds}
    assert by_tag["proxy"]["settings"]["vnext"][0]["address"] == "192.0.2.1"
    assert _sockopt(by_tag["proxy"])["dialerProxy"] == CHAIN_MAIN_TAG
    assert _sockopt(by_tag[CHAIN_MAIN_TAG])["dialerProxy"] == CHAIN_FRONT_TAG
    assert "dialerProxy" not in _sockopt(by_tag[CHAIN_FRONT_TAG])
    assert main.outbound.get("tag") is None  # stored node is never mutated


def test_xray_front_hop_inherits_existing_dialer() -> None:
    main = _vless("main", "203.0.113.1")
    front = _socks("front", "198.51.100.1")
    chain = resolve_proxy_chain(_settings("front"), [main, front], main)
    main_outbound = dict(main.outbound, tag="proxy")
    main_outbound["streamSettings"] = {"security": "tls", "sockopt": {"dialerProxy": "__protect"}}
    outbounds = [main_outbound]

    apply_xray_proxy_chain(outbounds, chain)

    by_tag = {item["tag"]: item for item in outbounds}
    assert _sockopt(by_tag["proxy"])["dialerProxy"] == CHAIN_FRONT_TAG
    assert _sockopt(by_tag[CHAIN_FRONT_TAG])["dialerProxy"] == "__protect"


def test_xray_skips_singbox_only_hop() -> None:
    main = _vless("main", "203.0.113.1")
    hop = _hysteria2("hy2", "198.51.100.1")
    chain = resolve_proxy_chain(_settings(exit_="hy2"), [main, hop], main)
    outbounds = [dict(main.outbound, tag="proxy")]

    assert apply_xray_proxy_chain(outbounds, chain) == ()
    assert [item["tag"] for item in outbounds] == ["proxy"]
    assert chain.notes


# ---- sing-box --------------------------------------------------------------

def test_singbox_native_chain_uses_detours_and_disables_hot_switch() -> None:
    main = _vless("main", "203.0.113.1")
    front = _socks("front", "198.51.100.1")
    exit_ = _hysteria2("exit", "exit.example.com")
    chain = resolve_proxy_chain(_settings("front", "exit"), [main, front, exit_], main)

    plan = _plan_singbox(main, chain, enable_hot_switch=True, hot_switch_nodes=[main, front, exit_])
    dials = _all_dials(plan.singbox_config)

    assert plan.outcome == "native_singbox"
    assert not plan.clash_api_selector
    assert dials["proxy"]["type"] == "hysteria2"
    assert dials["proxy"]["detour"] == CHAIN_MAIN_TAG
    assert dials["proxy"]["domain_resolver"] == "bootstrap-dns"
    assert dials[CHAIN_MAIN_TAG]["type"] == "vless"
    assert dials[CHAIN_MAIN_TAG]["detour"] == CHAIN_FRONT_TAG
    assert dials[CHAIN_FRONT_TAG]["type"] == "socks"
    assert "detour" not in dials[CHAIN_FRONT_TAG]
    assert plan.singbox_config["route"]["final"] == "proxy"


def test_singbox_without_chain_is_unchanged() -> None:
    main = _vless("main", "203.0.113.1")
    plan = _plan_singbox(main, None)
    dials = _all_dials(plan.singbox_config)
    assert dials["proxy"]["type"] == "vless"
    assert CHAIN_FRONT_TAG not in dials and CHAIN_MAIN_TAG not in dials


def test_hybrid_sidecar_chain_keeps_protect_dialer_on_front_hop(monkeypatch) -> None:
    import xray_fluent.engines.singbox.runtime_planner as planner

    main = _vless("main", "203.0.113.1")
    monkeypatch.setattr(planner, "_node_should_use_xray_sidecar", lambda node, *a, **k: node is main)
    main.outbound["streamSettings"] = {
        "network": "xhttp",
        "security": "tls",
        "tlsSettings": {"serverName": "server.example.com"},
        "xhttpSettings": {"path": "/", "mode": "auto"},
    }
    front = _socks("front", "198.51.100.1")
    chain = resolve_proxy_chain(_settings("front"), [main, front], main)

    plan = _plan_singbox(
        main,
        chain,
        preferred_relay_port=29001,
        preferred_protect_port=29002,
        preferred_protect_password="secret",
        enable_final_fragment=False,
    )

    assert plan.outcome == "hybrid_xray_sidecar"
    sidecar = {item["tag"]: item for item in plan.xray_sidecar.config["outbounds"]}
    protect_tag = [tag for tag in sidecar if tag.startswith("__app_hybrid_protect")][0]
    assert _sockopt(sidecar["proxy"])["dialerProxy"] == CHAIN_FRONT_TAG
    assert _sockopt(sidecar[CHAIN_FRONT_TAG])["dialerProxy"] == protect_tag
