"""Catalog parsing and per-server-kind strategies (files only, no winws2 runs)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from xray_fluent import zapret_strategies as strategies


def _catalog(tmp_path, transport: str, text: str, local: str = ""):
    (tmp_path / f"{transport}.txt").write_text(text, encoding="utf-8")
    if local:
        (tmp_path / f"{transport}.local.txt").write_text(local, encoding="utf-8")
    return strategies.load_catalog(transport, tmp_path)


def test_catalog_sections_and_local_override(tmp_path) -> None:
    catalog = _catalog(
        tmp_path,
        "tcp",
        "# header\n[one]\nname = One\nlabel = Stable\n--lua-desync=multisplit:pos=1\n"
        "[two]\n--payload=tls_client_hello\n--lua-desync=fake:blob=tls_google\n",
        "[one]\nname = One local\n--lua-desync=split\n",
    )

    assert set(catalog) == {"one", "two"}
    assert catalog["one"].name == "One local" and catalog["one"].args == ("--lua-desync=split",)
    assert catalog["two"].name == "two" and catalog["two"].transport == "tcp"
    assert catalog["two"].args == ("--payload=tls_client_hello", "--lua-desync=fake:blob=tls_google")


def test_catalog_rejects_unsafe_and_unresolved_entries(tmp_path) -> None:
    catalog = _catalog(
        tmp_path,
        "udp",
        "[filter]\n--filter-udp=443\n--lua-desync=fake\n"
        "[no_desync]\n--payload=quic_initial\n"
        "[unknown_blob]\n--lua-desync=fake:blob=nope_blob\n"
        "[ok]\nlabel = recommended\n--lua-desync=fake:blob=quic_google:repeats=6\n",
    )

    assert list(catalog) == ["ok"]
    assert catalog["ok"].label == "recommended"


def test_names_without_emoji_and_unique(tmp_path) -> None:
    catalog = _catalog(
        tmp_path,
        "tcp",
        "[a]\nname = \U0001f3ad\u2702\ufe0f TLS Fake + Split\n--lua-desync=split\n"
        "[b]\nname = Same\n--lua-desync=split\n[c]\nname = same\n--lua-desync=split\n[d]\nname = \U0001f525\n--lua-desync=split\n",
    )

    assert catalog["a"].name == "TLS Fake + Split"
    assert {catalog["b"].name, catalog["c"].name} == {"Same (b)", "same (c)"}
    assert catalog["d"].name == "d"


def test_shipped_names_are_clean() -> None:
    for kind in strategies.SERVER_KINDS:
        names = [entry.name for entry in strategies.kind_catalog(kind).values()]
        assert len({name.casefold() for name in names}) == len(names)
        assert all(name == strategies.clean_strategy_name(name) and name for name in names)


def test_parse_strategy_lines_validation() -> None:
    assert strategies.parse_strategy_lines("# c\n--payload=all\n--lua-desync=pass\n") == (
        "--payload=all",
        "--lua-desync=pass",
    )
    for bad in ("--lua-desync=fake --new", "--wf-tcp-out=443\n--lua-desync=fake", "--payload=all"):
        with pytest.raises(ValueError):
            strategies.parse_strategy_lines(bad)


def test_global_args_declare_lua_and_blobs() -> None:
    args = (
        "--lua-desync=fakemultisplit:fake_blob=fake_default_tls:pos=1",
        "--lua-desync=fake:blob=tls_google:repeats=2",
        "--lua-desync=fake:blob=0x00",
    )
    assert strategies.blob_names_in_args(args) == ("tls_google",)
    assert strategies.strategy_global_args(args) == (
        *strategies.CORE_LUA_INITS,
        "--lua-init=@lua/fakemultisplit.lua",
        "--blob=tls_google:@bin/tls_clienthello_www_google_com.bin",
    )


def test_defaults_exist_in_shipped_catalogs() -> None:
    for kind in strategies.SERVER_KINDS:
        strategy = strategies.strategy_for(kind)
        assert strategy is not None, kind
        assert strategy.strategy_id == strategies.DEFAULT_STRATEGIES[kind]
        assert strategy.transport == strategies.KIND_TRANSPORT[kind]
    assert strategies.missing_blob_files() == ()


def test_strategy_for_falls_back_to_default() -> None:
    assert strategies.strategy_for("tcp", "no-such-id").strategy_id == strategies.DEFAULT_STRATEGIES["tcp"]
    assert strategies.strategy_for("tcp", "pass").strategy_id == "pass"


def test_server_strategy_binding_values() -> None:
    assert strategies.server_strategy_preset("") == "@server"
    assert strategies.server_strategy_preset("alt9") == "@server:alt9"
    assert strategies.is_server_strategy("@server") and strategies.is_server_strategy("@server:x")
    assert not strategies.is_server_strategy("general.txt") and not strategies.is_server_strategy("")
    assert strategies.server_strategy_id("@server:alt9") == "alt9"
    assert strategies.server_strategy_id("@server") == ""


def test_sort_key_orders_by_label() -> None:
    def item(name: str, label: str):
        return strategies.Strategy(name, "tcp", name, ("--lua-desync=pass",), label=label)

    ordered = sorted([item("b", ""), item("c", "caution"), item("a", "stable"), item("z", "recommended")],
                     key=strategies.strategy_sort_key)
    assert [s.name for s in ordered] == ["z", "a", "c", "b"]


@pytest.mark.parametrize(
    ("scheme", "outbound", "kind"),
    [
        ("vless", {"protocol": "vless", "streamSettings": {"network": "ws"}}, "tcp"),
        ("trojan", {"type": "trojan"}, "tcp"),
        ("hysteria2", {"type": "hysteria2"}, "quic"),
        ("tuic", {}, "quic"),
        ("vmess", {"protocol": "vmess", "streamSettings": {"network": "kcp"}}, "quic"),
        ("wireguard", {"type": "wireguard"}, "wireguard"),
        ("awg", {}, "wireguard"),
    ],
)
def test_node_server_kind(scheme, outbound, kind) -> None:
    assert strategies.node_server_kind(SimpleNamespace(scheme=scheme, outbound=outbound)) == kind
