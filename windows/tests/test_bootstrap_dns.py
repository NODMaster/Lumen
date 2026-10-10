"""Trusted bootstrap resolution of server names (no network: all lookups are fakes)."""

from __future__ import annotations

import struct

import pytest

from xray_fluent import bootstrap_dns


def _answer(query: bytes, rcode: int, addresses: list[bytes], qtype: int = 1) -> bytes:
    ident = query[:2]
    question = query[12:]
    header = ident + struct.pack(">HHHHH", 0x8180 | rcode, 1, len(addresses), 0, 0)
    body = b""
    for raw in addresses:
        body += b"\xc0\x0c" + struct.pack(">HHIH", qtype, 1, 60, len(raw)) + raw
    return header + question + body


def test_query_and_response_round_trip() -> None:
    query = bootstrap_dns.build_query("vpn.example.com", 1)
    assert b"\x03vpn\x07example\x03com\x00" in query
    rcode, addresses = bootstrap_dns.parse_response(_answer(query, 0, [bytes([198, 51, 100, 7])]))
    assert rcode == 0 and addresses == ["198.51.100.7"]
    rcode, addresses = bootstrap_dns.parse_response(_answer(query, 3, []))
    assert rcode == 3 and addresses == []


def test_usable_address_rejects_fake_ip_and_specials() -> None:
    assert bootstrap_dns.usable_address("198.51.100.7")
    assert bootstrap_dns.usable_address("2001:db8::1")
    for bad in ("198.18.0.5", "198.19.255.1", "0.0.0.0", "127.0.0.1", "224.0.0.1", "nope"):
        assert not bootstrap_dns.usable_address(bad)


@pytest.fixture(autouse=True)
def _no_cache(monkeypatch):
    monkeypatch.setattr(bootstrap_dns, "_cache", None)


def test_doh_wins_over_system(monkeypatch) -> None:
    def system(_host):
        raise AssertionError("system resolver must not be asked")

    result = bootstrap_dns.resolve_bootstrap("vpn.example.com", doh=lambda h: {"198.51.100.7"}, system=system)
    assert result.source == "doh" and result.addresses == {"198.51.100.7"}


def test_system_used_when_doh_fails_and_fake_ip_ignored() -> None:
    def doh(_host):
        raise bootstrap_dns.BootstrapDnsError("blocked")

    result = bootstrap_dns.resolve_bootstrap("vpn.example.com", doh=doh, system=lambda h: {"198.18.0.9", "203.0.113.5"})
    assert result.source == "system" and result.addresses == {"203.0.113.5"}


def test_name_not_found_is_final() -> None:
    def doh(_host):
        raise bootstrap_dns.BootstrapNameNotFound("vpn.example.com")

    with pytest.raises(bootstrap_dns.BootstrapNameNotFound):
        bootstrap_dns.resolve_bootstrap("vpn.example.com", doh=doh, system=lambda h: {"203.0.113.5"})


def test_literal_needs_no_lookup() -> None:
    result = bootstrap_dns.resolve_bootstrap("[2001:db8::1]", doh=None, system=lambda h: set())
    assert result.source == "literal" and result.addresses == {"2001:db8::1"}


def test_last_known_good_cache(monkeypatch, tmp_path) -> None:
    now = [1_000_000.0]
    cache = bootstrap_dns.BootstrapCache(tmp_path / "lkg.json", clock=lambda: now[0])
    monkeypatch.setattr(bootstrap_dns, "_cache", cache)

    bootstrap_dns.resolve_bootstrap("vpn.example.com", doh=lambda h: {"198.51.100.7"}, system=lambda h: set())

    def down(_host):
        raise OSError("offline")

    result = bootstrap_dns.resolve_bootstrap("VPN.example.com.", doh=down, system=down)
    assert result.source == "cache" and result.addresses == {"198.51.100.7"}

    now[0] += bootstrap_dns.CACHE_MAX_AGE_SEC + 1
    with pytest.raises(OSError):
        bootstrap_dns.resolve_bootstrap("vpn.example.com", doh=down, system=down)


def test_system_answers_are_not_cached(monkeypatch, tmp_path) -> None:
    cache = bootstrap_dns.BootstrapCache(tmp_path / "lkg.json")
    monkeypatch.setattr(bootstrap_dns, "_cache", cache)

    def down(_host):
        raise OSError("offline")

    bootstrap_dns.resolve_bootstrap("vpn.example.com", doh=down, system=lambda h: {"203.0.113.5"})
    assert cache.lookup("vpn.example.com") == []


def test_resolve_doh_first_answer_and_nxdomain() -> None:
    def lookup(server, host, timeout):
        if server == "bad":
            raise OSError("reset")
        return {"198.51.100.7"}

    assert bootstrap_dns.resolve_doh("x.example", servers=("bad", "good"), lookup=lookup, timeout=0.5) == {"198.51.100.7"}

    def missing(server, host, timeout):
        raise bootstrap_dns.BootstrapNameNotFound(host)

    with pytest.raises(bootstrap_dns.BootstrapNameNotFound):
        bootstrap_dns.resolve_doh("x.example", servers=("a", "b"), lookup=missing, timeout=0.5)

    def broken(server, host, timeout):
        raise OSError("down")

    with pytest.raises(bootstrap_dns.BootstrapDnsError) as info:
        bootstrap_dns.resolve_doh("x.example", servers=("a", "b"), lookup=broken, timeout=0.5)
    assert not isinstance(info.value, bootstrap_dns.BootstrapNameNotFound)


def test_direct_doh_by_ip_sends_no_sni() -> None:
    from xray_fluent.engines.singbox.runtime_planner import _build_dns_server

    direct = _build_dns_server("bootstrap-dns", "1.1.1.1", "https", "")
    proxied = _build_dns_server("proxy-dns", "8.8.8.8", "https", "")

    assert direct["tls"] == {"server_name": "cloudflare-dns.com", "disable_sni": True}
    assert proxied["tls"] == {"server_name": "dns.google"}
