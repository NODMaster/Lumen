from __future__ import annotations

import io
import json
import random

import pytest

from xray_fluent import warp_generator as warp
from xray_fluent.link_parser import normalize_node_outbound, validate_node_outbound

AWG_REGISTRATION = {
    "privKey": "aGVsbG9oZWxsb2hlbGxvaGVsbG9oZWxsb2hlbGxvMTI=",
    "peer_pub": "bmqxbXbVq9xwU3dTEsTuhTPiwKVvk9rbmEtiwbI+Ix0=",
    "client_ipv4": "172.16.0.2",
    "client_ipv6": "2606:4700:110:8a36::1",
}
MASQUE_REGISTRATION = {
    "privKey": "MHcCAQEEIA25zQLXqGd935Et7ihZptBZTgHAOt1nUqGMQi+AfLK3oAoGCCqGSM49AwEHoUQDQgAE1bRHAEiia2r7rfYRVZMIEaEAb4pQSKlQeZ4+bOnrDVgru0VwW+uq7c182uLtUjSuNDMzhaLqnBl998/JOcl1Sw==",
    "peer_pub": "MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAEIaU7MToJm9NKp8YfGxR6r+/h4mcG7SxI8tsW8OR1A5tv/zCzVbCRRh2t87/kxnP6lAy0lkr7qYwu+ox+k3dr6w==",
    "client_ipv4": "172.16.0.2",
    "client_ipv6": "2606:4700:cf1:1000::1",
}


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_exc) -> None:
        self.close()


def _fake_network(responses: dict[str, object], calls: list):
    def open_url(request, timeout):
        calls.append((request.full_url, dict(request.header_items()), timeout))
        value = responses.get(request.full_url)
        if isinstance(value, Exception) or value is None:
            raise value or OSError("unreachable")
        return _Response(json.dumps(value).encode("utf-8"))

    return open_url


def test_awg_config_mirrors_generator_defaults() -> None:
    registration = warp.parse_registration(AWG_REGISTRATION)
    config = warp.build_awg_config(registration, warp.AWG_PROFILES[1][1], "162.159.192.1:4500")
    assert "PrivateKey = " + AWG_REGISTRATION["privKey"] in config
    assert "Address = 172.16.0.2\n" in config
    assert "DNS = 1.1.1.1, 1.0.0.1\n" in config
    assert "MTU = 1280\n" in config
    assert "Jc = 4\nJmin = 40\nJmax = 70\n" in config
    assert "H1 = 1\nH2 = 2\nH3 = 3\nH4 = 4\n" in config
    assert "I1 = <b 0xc400000001015c" in config
    assert "AllowedIPs = 0.0.0.0/0, ::/0\n" in config
    assert config.endswith("Endpoint = 162.159.192.1:4500\n")


def test_random_endpoint_uses_known_warp_ranges() -> None:
    rng = random.Random(7)
    for _ in range(200):
        host, port = warp.random_endpoint(rng).rsplit(":", 1)
        assert int(port) in warp.WARP_ENDPOINT_PORTS
        assert host == "engage.cloudflareclient.com" or any(
            host.startswith(prefix) and 1 <= int(host[len(prefix):]) <= 10
            for prefix in warp.WARP_ENDPOINT_PREFIXES
            if prefix.endswith(".")
        )


def test_generated_nodes_are_valid_and_grouped() -> None:
    calls: list = []
    open_url = _fake_network(
        {
            warp.AWG_DATA_ENDPOINTS[0]: AWG_REGISTRATION,
            warp.MASQUE_DATA_ENDPOINTS[0]: MASQUE_REGISTRATION,
        },
        calls,
    )
    result = warp.generate_warp_nodes(open_url, rng=random.Random(1))
    assert result.errors == []
    assert [node.scheme for node in result.nodes] == ["awg", "awg", "awg", "masque", "masque"]
    assert {node.group for node in result.nodes} == {warp.WARP_GROUP}
    assert len({node.name for node in result.nodes}) == 5
    for node in result.nodes:
        normalize_node_outbound(node)
        assert validate_node_outbound(node) is None
    sip = result.nodes[2].outbound["singbox"]["amnezia"]
    assert sip["i1"].startswith("<b 0x494e56495445") and sip["i2"].startswith("<b 0x5349502f")
    masque = [node.outbound["singbox"] for node in result.nodes[3:]]
    assert [item["use_http2"] for item in masque] == [False, True]
    assert all(item["server"] == warp.MASQUE_SERVER and item["tls"]["server_name"] == warp.MASQUE_SNI for item in masque)
    awg_headers = {key.lower(): value for key, value in calls[0][1].items()}
    assert awg_headers["x-client"] == "WARP"


def test_falls_back_through_endpoints_and_reports_partial_failure() -> None:
    calls: list = []
    open_url = _fake_network(
        {
            warp.AWG_DATA_ENDPOINTS[0]: OSError("HTTP 429"),
            warp.AWG_DATA_ENDPOINTS[1]: {"error": "usage_exceeded"},
            warp.AWG_DATA_ENDPOINTS[2]: AWG_REGISTRATION,
        },
        calls,
    )
    result = warp.generate_warp_nodes(open_url, rng=random.Random(2))
    assert [node.scheme for node in result.nodes] == ["awg", "awg", "awg"]
    assert len(result.errors) == 1 and result.errors[0].startswith("MASQUE:")
    requested = [url for url, _headers, _timeout in calls]
    assert requested[:3] == list(warp.AWG_DATA_ENDPOINTS[:3])
    assert requested[3:] == list(warp.MASQUE_DATA_ENDPOINTS)


def test_total_failure_raises() -> None:
    with pytest.raises(warp.WarpGenerationError):
        warp.generate_warp_nodes(_fake_network({}, []))


def test_cancelled_generation_stops_requests() -> None:
    calls: list = []
    with pytest.raises(warp.WarpGenerationError):
        warp.generate_warp_nodes(_fake_network({}, calls), cancelled=lambda: True)
    assert calls == []


@pytest.mark.parametrize(
    "payload",
    [None, [], {"privKey": "a"}, {"privKey": "a b", "peer_pub": "c", "client_ipv4": "1.1.1.1"}],
)
def test_invalid_registrations_are_rejected(payload) -> None:
    with pytest.raises(warp.WarpGenerationError):
        warp.parse_registration(payload)
