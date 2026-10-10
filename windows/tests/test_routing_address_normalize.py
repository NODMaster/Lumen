from __future__ import annotations

import pytest

from xray_fluent.routing_rule_import import normalize_routing_address, split_routing_addresses


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("example.com", "example.com"),
        ("  EXAMPLE.com.  ", "example.com"),
        ("https://www.Example.com:8443/path?q=1#top", "example.com"),
        ("http://user:pass@sub.example.org/", "sub.example.org"),
        ("//cdn.example.net/lib.js", "cdn.example.net"),
        ("example.com/some/page", "example.com"),
        ("example.com:443", "example.com"),
        ("www.example.com", "example.com"),
        ("www.com", "www.com"),
        ("*.Example.com", "*.example.com"),
        (".example.com", "*.example.com"),
        ("пример.рф", "xn--e1afmkfd.xn--p1ai"),
        ("https://пример.рф/путь", "xn--e1afmkfd.xn--p1ai"),
        ("1.2.3.4", "1.2.3.4"),
        ("http://1.2.3.4:8080/x", "1.2.3.4"),
        ("10.0.0.1/8", "10.0.0.0/8"),
        ("[2001:db8::1]:443", "2001:db8::1"),
        ("2001:DB8::/32", "2001:db8::/32"),
        ("domain:WWW.Example.com", "domain:www.example.com"),
        ("full:https://Api.Example.com/v1", "full:api.example.com"),
        ("keyword:Google", "keyword:Google"),
        ("regexp:^.*\\.example\\.com$", "regexp:^.*\\.example\\.com$"),
        ("geosite:category-ads-all", "geosite:category-ads-all"),
        ("geoip:private", "geoip:private"),
    ],
)
def test_normalize_routing_address(raw: str, expected: str) -> None:
    assert normalize_routing_address(raw) == expected


@pytest.mark.parametrize("raw", ["", "   ", "localhost", "bad_host!", "10.0.0.300", "-a.com", "*.", "domain:", "https://"])
def test_normalize_rejects_invalid(raw: str) -> None:
    assert normalize_routing_address(raw) is None


def test_split_routing_addresses() -> None:
    assert split_routing_addresses("a.com, b.com\nc.com;d.com  e.com") == ["a.com", "b.com", "c.com", "d.com", "e.com"]
    assert split_routing_addresses("regexp:a, b") == ["regexp:a, b"]
    assert split_routing_addresses("") == []
