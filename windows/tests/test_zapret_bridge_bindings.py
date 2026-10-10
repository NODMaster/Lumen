"""Bridge rows of "run together with server" (no QML engine, fake controller)."""

from __future__ import annotations

from types import SimpleNamespace

from xray_fluent import zapret_strategies
from xray_fluent.qml_app.bridge.app_bridge import AppBridge

_OUTBOUNDS = {"vless": {"protocol": "vless"}, "hysteria2": {"type": "hysteria2"}}


class _Bridge:
    _node_option_label = staticmethod(AppBridge._node_option_label)
    _zapret_strategy_options = AppBridge._zapret_strategy_options
    _zapret_binding_choices = AppBridge._zapret_binding_choices
    _zapret_binding_value = AppBridge._zapret_binding_value

    def __init__(self, presets: dict[str, str], selected: str = "") -> None:
        nodes = [
            SimpleNamespace(id=node_id, name=f"node-{node_id}", group="", scheme=scheme, outbound=_OUTBOUNDS[scheme])
            for node_id, scheme in (("a", "vless"), ("b", "vless"), ("q", "hysteria2"))
        ]
        by_id = {node.id: node for node in nodes}
        self.stored: list[dict[str, str]] = []
        self.controller = SimpleNamespace(
            state=SimpleNamespace(
                nodes=nodes, settings=SimpleNamespace(zapret_server_presets=presets, zapret_preset="manual.txt")
            ),
            selected_node=by_id.get(selected),
            connected=False,
            _active_session=None,
            _get_node_by_id=by_id.get,
        )
        self._store_zapret_bindings = self.stored.append

    def zapretPresets(self):
        return [{"name": "general.txt"}, {"name": "manual.txt"}]


def _other(kind: str) -> str:
    default = zapret_strategies.DEFAULT_STRATEGIES[kind]
    return next(sid for sid in zapret_strategies.kind_catalog(kind) if sid != default)


def test_selected_server_is_offered_first() -> None:
    bridge = _Bridge({"a": ""}, selected="q")

    options = AppBridge.zapretServerOptions(bridge)

    assert [item["value"] for item in options] == ["q", "b"]
    assert options[0]["label"].startswith("node-q (")
    assert "(" not in options[1]["label"]


def test_picker_names_the_automatic_strategy() -> None:
    choices = AppBridge.zapretBindingChoices(_Bridge({}), "q")
    auto = zapret_strategies.strategy_for("quic")

    assert choices[0]["value"] == "@server"
    assert choices[0]["label"].endswith(": " + auto.name)
    assert [c["value"] for c in choices[1:3]] == ["general.txt", "manual.txt"]
    values = [c["value"] for c in choices]
    assert "" not in values  # no "current preset" entry
    assert "@server:" + auto.strategy_id not in values  # the automatic one is listed once
    assert "@server:" + _other("quic") in values
    assert all("·" not in c["label"] for c in choices)


def test_rows_point_at_their_choice() -> None:
    other = _other("quic")
    bridge = _Bridge({"a": "@server", "q": "@server:" + other, "b": "general.txt", "x": ""})

    rows = {row["nodeId"]: row for row in AppBridge.zapretServerBindings(bridge)}

    a, q, b = rows["a"], rows["q"], rows["b"]
    assert a["strategyMode"] and a["kindTitle"] == "TCP" and a["choiceIndex"] == 0
    assert q["kindTitle"] == "QUIC" and q["choices"][q["choiceIndex"]]["value"] == "@server:" + other
    assert not b["strategyMode"] and b["choices"][b["choiceIndex"]]["value"] == "general.txt"
    assert rows["x"]["missingNode"] and rows["x"]["choices"] == []


def test_legacy_current_preset_binding_shows_the_running_preset() -> None:
    bridge = _Bridge({"b": ""})

    row = AppBridge.zapretServerBindings(bridge)[0]

    assert row["choiceIndex"] == -1
    assert row["placeholder"].endswith(": manual.txt")


def test_binding_values_are_normalized() -> None:
    bridge = _Bridge({})
    tcp_default = zapret_strategies.DEFAULT_STRATEGIES["tcp"]

    AppBridge.setZapretServerBinding(bridge, "a", "@server:" + _other("tcp"))
    assert bridge.stored[-1] == {"a": "@server:" + _other("tcp")}

    bridge.controller.state.settings.zapret_server_presets = dict(bridge.stored[-1])
    AppBridge.setZapretServerBinding(bridge, "a", "@server:" + tcp_default)
    assert bridge.stored[-1] == {"a": "@server"}

    count = len(bridge.stored)
    AppBridge.setZapretServerBinding(bridge, "a", "@server:no-such-id")
    AppBridge.setZapretServerBinding(bridge, "missing", "@server")
    assert len(bridge.stored) == count

    AppBridge.setZapretServerBinding(bridge, "a", "general.txt")
    assert bridge.stored[-1] == {"a": "general.txt"}
