"""Pure argv tests for limiting a Zapret preset to one server (no winws2 runs)."""

from __future__ import annotations

from types import SimpleNamespace

import xray_fluent.zapret_server_scope as scope_mod
import xray_fluent.zapret_strategies as strategies_mod
from xray_fluent.zapret_server_scope import (
    SERVER_STRATEGY_PRESET,
    ZapretServerScope,
    build_scoped_args,
    make_server_scope,
    merge_global_args,
    node_transports,
    resolve_server_ips,
    split_preset_args,
)

SERVER_PRESET = [
    "--lua-init=@lua/zapret-lib.lua",
    "--wf-tcp-out=80,443",
    "--wf-udp-out=443",
    "--blob=tls1:@bin/tls_1.bin",
    "--name=exclude",
    "--filter-tcp=80,443",
    "--hostlist=lists/netrogat.txt",
    "--lua-desync=pass",
    "--new",
    "--name=youtube",
    "--filter-tcp=443",
    "--hostlist=lists/youtube.txt",
    "--lua-desync=fake:blob=tls1",
    "--new",
    "--name=all",
    "--filter-tcp=80,443-65535",
    "--ipset-exclude=lists/ipset-ru.txt",
    "--payload=tls_client_hello",
    "--lua-desync=multisplit:pos=1",
    "--new",
    "--name=quic",
    "--filter-udp=443",
    "--filter-l7=quic",
    "--lua-desync=fake:blob=quic1",
]

MANUAL_PRESET = [
    "--lua-init=@lua/zapret-lib.lua",
    "--lua-init=@lua/custom.lua",
    "--wf-tcp-out=443,2053",
    "--blob=tls1:@bin/other.bin",
    "--name=discord",
    "--filter-tcp=443",
    "--hostlist=lists/discord.txt",
    "--lua-desync=split",
]


def _scope(**overrides) -> ZapretServerScope:
    values = dict(preset="srv", ips=("203.0.113.10",), port=8443, label="NL", tcp=True, udp=False)
    values.update(overrides)
    return ZapretServerScope(**values)


def test_server_profiles_only_match_the_server() -> None:
    args = build_scoped_args(SERVER_PRESET, _scope())
    _, profiles = split_preset_args(args)

    assert len(profiles) == 2
    for profile in profiles:
        assert profile[0].startswith("--name=Lumen server: NL")
        assert "--filter-tcp=8443" in profile
        assert "--ipset-ip=203.0.113.10" in profile
        assert not any(a.startswith(("--hostlist", "--ipset=", "--ipset-exclude", "--filter-l7")) for a in profile)
    # Generic "all sites" strategy first, exclusion (pass) profile dropped.
    assert "--lua-desync=multisplit:pos=1" in profiles[0]
    assert "--payload=tls_client_hello,http_req" in profiles[0]
    assert "--lua-desync=fake:blob=tls1" in profiles[1]
    assert not any("--lua-desync=pass" in p for p in profiles)


def test_manual_profiles_follow_unchanged_after_new() -> None:
    args = build_scoped_args(SERVER_PRESET, _scope(), MANUAL_PRESET)
    globals_, profiles = split_preset_args(args)

    assert profiles[-1] == [
        "--name=discord",
        "--filter-tcp=443",
        "--hostlist=lists/discord.txt",
        "--lua-desync=split",
    ]
    assert args.count("--new") == len(profiles) - 1
    assert globals_.count("--lua-init=@lua/zapret-lib.lua") == 1
    assert "--lua-init=@lua/custom.lua" in globals_
    assert [a for a in globals_ if a.startswith("--blob=tls1:")] == ["--blob=tls1:@bin/tls_1.bin"]


def test_windivert_filter_includes_server_port() -> None:
    args = build_scoped_args(SERVER_PRESET, _scope(), MANUAL_PRESET)
    wf_tcp = [a for a in args if a.startswith("--wf-tcp-out=")]
    assert wf_tcp == ["--wf-tcp-out=80,443,2053,8443"]

    merged = merge_global_args(["--wf-tcp-out=80,443-65535"], extra_ports={"--wf-tcp-out": 8443})
    assert merged == ["--wf-tcp-out=80,443-65535"]


def test_udp_server_uses_udp_profiles() -> None:
    args = build_scoped_args(SERVER_PRESET, _scope(tcp=False, udp=True, port=4433))
    _, profiles = split_preset_args(args)

    assert len(profiles) == 1
    assert "--filter-udp=4433" in profiles[0]
    assert "--payload=quic_initial,wireguard_initiation" in profiles[0]
    assert "--lua-desync=fake:blob=quic1" in profiles[0]
    assert any(a.startswith("--wf-udp-out=") and a.endswith(",4433") for a in args)


def test_server_profiles_never_touch_session_data() -> None:
    preset = [
        "--filter-tcp=443",
        "--payload=all",
        "--lua-desync=fake:blob=tls1:repeats=6:payload=all",
        "--new",
        "--filter-udp=443",
        "--payload=all",
        "--lua-desync=fake:blob=quic1:payload=all:repeats=10",
    ]
    args = build_scoped_args(preset, _scope(tcp=True, udp=True, port=443))
    assert "payload=all" not in " ".join(args)
    _, profiles = split_preset_args(args)
    assert "--lua-desync=fake:blob=tls1:repeats=6:payload=tls_client_hello,http_req" in profiles[0]
    assert "--lua-desync=fake:blob=quic1:payload=quic_initial,wireguard_initiation:repeats=10" in profiles[1]


def test_cached_server_ips_never_resolves(monkeypatch) -> None:
    def boom(*_args):
        raise AssertionError("no DNS lookup expected")

    monkeypatch.setattr(scope_mod.socket, "getaddrinfo", boom)
    monkeypatch.setattr(scope_mod, "_RESOLVE_CACHE", {"vpn.example.com": (scope_mod.time.monotonic(), ("198.51.100.9",))})
    assert scope_mod.cached_server_ips("vpn.example.com") == ("198.51.100.9",)
    assert scope_mod.cached_server_ips("other.example.com") == ()
    assert scope_mod.cached_server_ips("203.0.113.4") == ("203.0.113.4",)


def test_preset_without_strategies_gives_no_args() -> None:
    only_pass = ["--filter-tcp=443", "--hostlist=lists/x.txt", "--lua-desync=pass"]
    assert build_scoped_args(only_pass, _scope(), MANUAL_PRESET) == []


def test_node_transports() -> None:
    tcp_node = SimpleNamespace(scheme="vless", outbound={"protocol": "vless", "streamSettings": {"network": "ws"}})
    udp_node = SimpleNamespace(scheme="hysteria2", outbound={"type": "hysteria2"})
    kcp_node = SimpleNamespace(scheme="vmess", outbound={"protocol": "vmess", "streamSettings": {"network": "kcp"}})
    assert node_transports(tcp_node) == (True, False)
    assert node_transports(udp_node) == (False, True)
    assert node_transports(kcp_node) == (False, True)


def test_resolve_skips_fake_ip_and_reuses_last_real_answer(monkeypatch) -> None:
    answers = {"first": ["198.51.100.7"], "second": ["198.18.0.5"]}
    state = {"phase": "first"}

    def fake_getaddrinfo(host, *_args):
        return [(2, 1, 6, "", (ip, 0)) for ip in answers[state["phase"]]]

    def doh_down(_host):
        raise scope_mod.bootstrap_dns.BootstrapDnsError("blocked")

    monkeypatch.setattr(scope_mod, "_trusted_doh", doh_down)
    monkeypatch.setattr(scope_mod.bootstrap_dns, "_cache", None)
    monkeypatch.setattr(scope_mod.socket, "getaddrinfo", fake_getaddrinfo)
    monkeypatch.setattr(scope_mod, "_RESOLVE_CACHE", {})

    assert resolve_server_ips("vpn.example.com") == ("198.51.100.7",)
    state["phase"] = "second"
    assert resolve_server_ips("vpn.example.com") == ("198.51.100.7",)
    assert resolve_server_ips("203.0.113.4") == ("203.0.113.4",)
    assert resolve_server_ips("") == ()


def test_trusted_doh_answer_beats_isp_dns(monkeypatch) -> None:
    def isp(*_args):
        return [(2, 1, 6, "", ("10.10.34.35", 0))]  # ISP stub page for a blocked name

    monkeypatch.setattr(scope_mod, "_trusted_doh", lambda host: {"198.51.100.7"})
    monkeypatch.setattr(scope_mod.bootstrap_dns, "_cache", None)
    monkeypatch.setattr(scope_mod.socket, "getaddrinfo", isp)
    monkeypatch.setattr(scope_mod, "_RESOLVE_CACHE", {})

    assert resolve_server_ips("vpn.example.com") == ("198.51.100.7",)


def test_name_denied_by_trusted_resolvers_gives_nothing(monkeypatch) -> None:
    def missing(host):
        raise scope_mod.bootstrap_dns.BootstrapNameNotFound(host)

    monkeypatch.setattr(scope_mod, "_trusted_doh", missing)
    monkeypatch.setattr(scope_mod.bootstrap_dns, "_cache", None)
    monkeypatch.setattr(scope_mod.socket, "getaddrinfo", lambda *_a: [(2, 1, 6, "", ("203.0.113.5", 0))])
    monkeypatch.setattr(scope_mod, "_RESOLVE_CACHE", {})

    assert resolve_server_ips("gone.example.com") == ()


def _node(scheme: str, outbound: dict, port: int = 8443) -> SimpleNamespace:
    return SimpleNamespace(id="n1", name="NL", server="vpn.example.com", port=port, scheme=scheme, outbound=outbound)


def test_strategy_scope_per_server_kind() -> None:
    tcp = make_server_scope(_node("vless", {"protocol": "vless"}), SERVER_STRATEGY_PRESET, ["203.0.113.10"])
    quic = make_server_scope(_node("hysteria2", {"type": "hysteria2"}), SERVER_STRATEGY_PRESET, ["203.0.113.10"])
    wg = make_server_scope(_node("wireguard", {"type": "wireguard"}, 51820), SERVER_STRATEGY_PRESET, ["203.0.113.10"])

    assert tcp.uses_strategy and tcp.kind == "tcp" and tcp.tcp and not tcp.udp
    assert quic.kind == "quic" and quic.udp and not quic.tcp
    assert wg.kind == "wireguard" and wg.udp and wg.port == 51820
    assert tcp.strategy == strategies_mod.DEFAULT_STRATEGIES["tcp"]
    assert "стратегия" in tcp.title

    vanished = make_server_scope(_node("hysteria2", {"type": "hysteria2"}), "@server:no-such", ["203.0.113.10"])
    assert vanished.strategy == strategies_mod.DEFAULT_STRATEGIES["quic"]
    other_id = next(sid for sid in strategies_mod.kind_catalog("quic") if sid != vanished.strategy)
    chosen = make_server_scope(_node("hysteria2", {"type": "hysteria2"}), "@server:" + other_id, ["203.0.113.10"])
    assert chosen.strategy == other_id and chosen.uses_strategy and chosen.preset == SERVER_STRATEGY_PRESET


def test_strategy_scope_args_are_server_only() -> None:
    scope = make_server_scope(_node("wireguard", {"type": "wireguard"}, 51820), SERVER_STRATEGY_PRESET, ["203.0.113.10"])
    args = build_scoped_args([], scope, MANUAL_PRESET)
    globals_, profiles = split_preset_args(args)

    assert profiles[0][:3] == ["--name=Lumen server: NL", "--filter-udp=51820", "--ipset-ip=203.0.113.10"]
    assert tuple(profiles[0][3:]) == scope.strategy_args
    assert profiles[-1][0] == "--name=discord"
    assert any(a.startswith("--wf-udp-out=") and a.endswith("51820") for a in globals_)
    assert globals_.count("--lua-init=@lua/zapret-lib.lua") == 1


def test_signature_tracks_strategy_not_ips() -> None:
    node = _node("vless", {"protocol": "vless"})
    first = make_server_scope(node, SERVER_STRATEGY_PRESET, ["203.0.113.10"])
    moved = make_server_scope(node, SERVER_STRATEGY_PRESET, ["203.0.113.11"])
    other_id = next(sid for sid in strategies_mod.kind_catalog("tcp") if sid != first.strategy)
    changed = make_server_scope(node, "@server:" + other_id, ["203.0.113.10"])

    assert first.signature() == moved.signature()
    assert first.signature() != changed.signature()
    assert make_server_scope(node, "general.txt", ["203.0.113.10"]).signature() != first.signature()
