"""Controller-free tests for the "run Zapret together with a server" logic.

No real Zapret/WinDivert process is started and no DNS lookup is made: the
manager and the resolver are fakes.
"""

from __future__ import annotations

from types import SimpleNamespace

import xray_fluent.app_controller as app_controller
from xray_fluent.app_controller import AppController
from xray_fluent.models import AppSettings
from xray_fluent import zapret_strategies
from xray_fluent.zapret_server_scope import SERVER_STRATEGY_PRESET

_OUTBOUNDS = {
    "vless": {"protocol": "vless", "streamSettings": {"network": "tcp"}},
    "hysteria2": {"type": "hysteria2"},
    "wireguard": {"type": "wireguard"},
}


class _FakeZapret:
    def __init__(self) -> None:
        self.running = False
        self.current_preset = ""
        self.server_scope = None
        self.calls: list[tuple[str, str, str | None]] = []

    def start(self, preset: str, server_scope=None) -> None:
        self.calls.append(("start", preset, server_scope.preset if server_scope else None))
        self.running = True
        self.current_preset = preset
        self.server_scope = server_scope

    def stop(self) -> None:
        self.calls.append(("stop", self.current_preset, None))
        self.running = False
        self.current_preset = ""
        self.server_scope = None


class _FakeController:
    zapret_preset_for_node = AppController.zapret_preset_for_node
    sync_zapret_server_binding = AppController.sync_zapret_server_binding
    start_zapret_preset = AppController.start_zapret_preset
    stop_zapret_manual = AppController.stop_zapret_manual
    _prepare_zapret_scope_before_connect = AppController._prepare_zapret_scope_before_connect
    _maybe_autostart_zapret = AppController._maybe_autostart_zapret
    _on_zapret_stopped_for_binding = AppController._on_zapret_stopped_for_binding
    _zapret_pre_connect_target = AppController._zapret_pre_connect_target
    _zapret_pre_connect_host = AppController._zapret_pre_connect_host

    def __init__(self, settings: AppSettings) -> None:
        self.state = SimpleNamespace(settings=settings)
        self.zapret = _FakeZapret()
        self.connected = False
        self._active_session = None
        self._shutting_down = False
        self.selected_node = None
        self._zapret_scope_token = 0
        self._zapret_desired_scope = None
        self._zapret_binding_warned_node = ""
        self._zapret_autostart_done = False
        self._zapret_reconnect_signature = None
        self._transition_active = False
        self._resume_reconnect_pending = False
        self.transitions: list[str] = []
        self.schemes: dict[str, str] = {}
        self.resolved: dict[str, tuple[str, ...]] = {}
        self.lookups: list[str] = []
        self.logs: list[str] = []
        self.statuses: list[tuple[str, str]] = []
        self.status = SimpleNamespace(emit=lambda level, text: self.statuses.append((level, text)))

    def _log(self, text: str) -> None:
        self.logs.append(text)

    def _get_node_by_id(self, node_id: str):
        return SimpleNamespace(
            id=node_id,
            name=f"node-{node_id}",
            server=f"{node_id}.example.com",
            port=443,
            scheme=self.schemes.get(node_id, "vless"),
            outbound=_OUTBOUNDS[self.schemes.get(node_id, "vless")],
        )

    def _request_transition(self, reason: str) -> None:
        self.transitions.append(reason)

    def _resolve_zapret_server_ips(self, host: str, callback) -> None:
        self.lookups.append(host)
        callback(self.resolved.get(host, ("203.0.113.10",)))

    def _prefetch_zapret_server_ips(self) -> None:
        pass

    def connect_to(self, node_id: str) -> None:
        self.connected = True
        self._active_session = SimpleNamespace(node_id=node_id)
        self.sync_zapret_server_binding()

    def disconnect(self) -> None:
        self.connected = False
        self._active_session = None
        self.sync_zapret_server_binding()


def _controller(monkeypatch, *, elevated: bool = True, **settings) -> _FakeController:
    monkeypatch.setattr(app_controller, "is_process_elevated", lambda: elevated)
    return _FakeController(AppSettings(**settings))


def test_bound_preset_is_limited_to_the_server(monkeypatch) -> None:
    ctl = _controller(monkeypatch, zapret_server_presets={"a": "general.txt"})

    ctl.connect_to("a")

    assert ctl.zapret.calls == [("start", "", "general.txt")]
    scope = ctl.zapret.server_scope
    assert scope.ips == ("203.0.113.10",)
    assert scope.port == 443 and scope.tcp and not scope.udp
    assert scope.node_id == "a"

    ctl.disconnect()
    assert ctl.zapret.calls[-1] == ("stop", "", None)
    assert not ctl.zapret.running


def test_manual_preset_keeps_running_next_to_the_server_preset(monkeypatch) -> None:
    ctl = _controller(monkeypatch, zapret_server_presets={"a": "discord.txt"})
    ctl.zapret.start("manual.txt")
    ctl.zapret.calls.clear()

    ctl.connect_to("a")
    assert ctl.zapret.calls == [("start", "manual.txt", "discord.txt")]

    ctl.disconnect()
    assert ctl.zapret.calls[-1] == ("start", "manual.txt", None)
    assert ctl.zapret.server_scope is None


def test_unbound_server_leaves_zapret_alone(monkeypatch) -> None:
    ctl = _controller(monkeypatch, zapret_server_presets={"a": "general.txt"})
    ctl.zapret.start("manual.txt")
    ctl.zapret.calls.clear()

    ctl.connect_to("b")
    ctl.disconnect()

    assert ctl.zapret.calls == []
    assert ctl.zapret.current_preset == "manual.txt"


def test_same_server_is_not_restarted(monkeypatch) -> None:
    ctl = _controller(monkeypatch, zapret_server_presets={"a": "general.txt"})

    ctl.connect_to("a")
    ctl.sync_zapret_server_binding()

    assert len(ctl.zapret.calls) == 1


def test_manual_start_keeps_server_scope(monkeypatch) -> None:
    ctl = _controller(monkeypatch, zapret_server_presets={"a": "general.txt"})
    ctl.connect_to("a")

    ctl.start_zapret_preset("manual.txt")

    assert ctl.zapret.calls[-1] == ("start", "manual.txt", "general.txt")


def test_unresolved_server_warns_and_keeps_manual(monkeypatch) -> None:
    ctl = _controller(monkeypatch, zapret_server_presets={"a": "general.txt"})
    ctl.resolved["a.example.com"] = ()
    ctl.zapret.start("manual.txt")
    ctl.zapret.calls.clear()

    ctl.connect_to("a")

    assert ctl.zapret.calls == []
    assert ctl.statuses and ctl.statuses[0][0] == "warning"


def test_empty_binding_uses_current_preset(monkeypatch) -> None:
    ctl = _controller(monkeypatch, zapret_preset="default.txt", zapret_server_presets={"a": ""})

    ctl.connect_to("a")

    assert ctl.zapret.calls == [("start", "", "default.txt")]


def test_not_elevated_warns_once_and_does_not_start(monkeypatch) -> None:
    ctl = _controller(monkeypatch, elevated=False, zapret_server_presets={"a": "general.txt"})

    ctl.connect_to("a")
    ctl.sync_zapret_server_binding()

    assert ctl.zapret.calls == []
    assert ctl.lookups == []
    assert len(ctl.statuses) == 1 and ctl.statuses[0][0] == "warning"


def test_user_stop_is_not_undone_on_disconnect(monkeypatch) -> None:
    ctl = _controller(monkeypatch, zapret_server_presets={"a": "general.txt"})
    ctl.connect_to("a")
    ctl.zapret.stop()
    ctl._on_zapret_stopped_for_binding()
    ctl.zapret.calls.clear()

    ctl.disconnect()

    assert ctl.zapret.calls == []


def test_autostart_runs_once_when_enabled(monkeypatch) -> None:
    ctl = _controller(monkeypatch, zapret_autostart=True, zapret_preset="default.txt")

    ctl._maybe_autostart_zapret()
    ctl.zapret.stop()
    ctl._maybe_autostart_zapret()

    assert ctl.zapret.calls == [("start", "default.txt", None), ("stop", "default.txt", None)]


def test_autostart_disabled_does_nothing(monkeypatch) -> None:
    ctl = _controller(monkeypatch, zapret_autostart=False, zapret_preset="default.txt")

    ctl._maybe_autostart_zapret()

    assert ctl.zapret.calls == []


def test_stop_keeps_the_server_part(monkeypatch) -> None:
    ctl = _controller(monkeypatch, zapret_server_presets={"a": "general.txt"})
    ctl.zapret.start("manual.txt")
    ctl.connect_to("a")

    ctl.stop_zapret_manual()

    assert ctl.zapret.calls[-1] == ("start", "", "general.txt")
    ctl.stop_zapret_manual()
    assert ctl.zapret.calls[-1] == ("stop", "", None)


def test_server_part_starts_before_connect_from_cache(monkeypatch) -> None:
    ctl = _controller(monkeypatch, zapret_server_presets={"a": "general.txt"})
    monkeypatch.setattr(app_controller, "cached_server_ips", lambda host: ("203.0.113.10",))
    ctl.selected_node = ctl._get_node_by_id("a")

    ctl._prepare_zapret_scope_before_connect("connect")
    assert ctl.zapret.calls == [("start", "", "general.txt")]

    # The post-connect sync sees the same scope and does not restart winws2.
    ctl.connect_to("a")
    assert len(ctl.zapret.calls) == 1
    assert ctl.lookups == []


def test_no_pre_connect_start_without_cached_ip(monkeypatch) -> None:
    ctl = _controller(monkeypatch, zapret_server_presets={"a": "general.txt"})
    monkeypatch.setattr(app_controller, "cached_server_ips", lambda host: ())
    ctl.selected_node = ctl._get_node_by_id("a")

    ctl._prepare_zapret_scope_before_connect("connect")
    ctl._prepare_zapret_scope_before_connect("disconnect")

    assert ctl.zapret.calls == []


def test_server_presets_round_trip() -> None:
    settings = AppSettings(zapret_server_presets={"a": "general.txt", "b": ""})
    restored = AppSettings.from_dict(settings.to_dict())
    assert restored.zapret_server_presets == {"a": "general.txt", "b": ""}


def test_server_strategy_follows_server_kind(monkeypatch) -> None:
    ctl = _controller(monkeypatch, zapret_server_presets={"a": SERVER_STRATEGY_PRESET, "q": SERVER_STRATEGY_PRESET})
    ctl.schemes["q"] = "hysteria2"

    ctl.connect_to("a")
    scope = ctl.zapret.server_scope
    assert ctl.zapret.calls == [("start", "", SERVER_STRATEGY_PRESET)]
    assert scope.kind == "tcp" and scope.tcp and scope.strategy == zapret_strategies.DEFAULT_STRATEGIES["tcp"]

    ctl.disconnect()
    ctl.connect_to("q")
    scope = ctl.zapret.server_scope
    assert scope.kind == "quic" and scope.udp and not scope.tcp
    assert ctl.transitions == []  # another server: plain restart, no reconnect


def _other_strategy(kind: str) -> str:
    default = zapret_strategies.DEFAULT_STRATEGIES[kind]
    return next(sid for sid in zapret_strategies.kind_catalog(kind) if sid != default)


def test_strategy_change_while_connected_reconnects_through_new_strategy(monkeypatch) -> None:
    ctl = _controller(monkeypatch, zapret_server_presets={"a": SERVER_STRATEGY_PRESET})
    monkeypatch.setattr(app_controller, "cached_server_ips", lambda host: ("203.0.113.10",))
    ctl.connect_to("a")
    ctl.zapret.calls.clear()
    new_id = _other_strategy("tcp")

    ctl.state.settings.zapret_server_presets = {"a": "@server:" + new_id}
    ctl.sync_zapret_server_binding()

    assert ctl.transitions == ["zapret server strategy changed"]
    assert ctl._resume_reconnect_pending
    assert ctl.zapret.calls == []  # winws2 restarts inside the reconnect, before the handshake

    ctl.selected_node = ctl._get_node_by_id("a")
    ctl._prepare_zapret_scope_before_connect("reconnect")
    assert ctl.zapret.calls == [("start", "", SERVER_STRATEGY_PRESET)]
    assert ctl.zapret.server_scope.strategy == new_id

    ctl.sync_zapret_server_binding()  # post-connect sync: same scope, nothing more
    assert len(ctl.zapret.calls) == 1 and ctl.transitions == ["zapret server strategy changed"]
    assert ctl._zapret_reconnect_signature is None


def test_repeated_change_without_reconnect_restarts_in_place(monkeypatch) -> None:
    ctl = _controller(monkeypatch, zapret_server_presets={"a": SERVER_STRATEGY_PRESET})
    ctl.connect_to("a")
    ctl.state.settings.zapret_server_presets = {"a": "@server:" + _other_strategy("tcp")}
    ctl.sync_zapret_server_binding()
    ctl.zapret.calls.clear()

    # The reconnect did not re-scope winws2 (e.g. it was skipped): no reconnect loop.
    ctl.sync_zapret_server_binding()

    assert ctl.transitions == ["zapret server strategy changed"]
    assert ctl.zapret.calls == [("start", "", SERVER_STRATEGY_PRESET)]


def test_no_reconnect_while_transition_runs(monkeypatch) -> None:
    ctl = _controller(monkeypatch, zapret_server_presets={"a": SERVER_STRATEGY_PRESET})
    ctl.connect_to("a")
    ctl._transition_active = True
    ctl.state.settings.zapret_server_presets = {"a": "@server:" + _other_strategy("tcp")}

    ctl.sync_zapret_server_binding()

    assert ctl.transitions == []
    assert ctl.zapret.calls[-1] == ("start", "", SERVER_STRATEGY_PRESET)


def test_pre_connect_host_needs_lookup_only_without_cache(monkeypatch) -> None:
    ctl = _controller(monkeypatch, zapret_server_presets={"a": "general.txt"})
    cache: dict[str, tuple[str, ...]] = {}
    monkeypatch.setattr(app_controller, "cached_server_ips", lambda host: cache.get(host, ()))
    ctl.selected_node = ctl._get_node_by_id("a")

    assert ctl._zapret_pre_connect_host("connect") == "a.example.com"
    assert ctl._zapret_pre_connect_host("tun_hot_swap") == "a.example.com"
    assert ctl._zapret_pre_connect_host("disconnect") == ""
    cache["a.example.com"] = ("203.0.113.10",)
    assert ctl._zapret_pre_connect_host("connect") == ""
    ctl.selected_node = ctl._get_node_by_id("b")
    cache.clear()
    assert ctl._zapret_pre_connect_host("connect") == ""


def test_prefetch_learns_every_bound_server(monkeypatch) -> None:
    ctl = _controller(monkeypatch, zapret_server_presets={"a": "", "b": "x.txt", "c": SERVER_STRATEGY_PRESET})
    ctl.connected = True
    ctl._active_session = SimpleNamespace(node_id="a")
    monkeypatch.setattr(app_controller, "cached_server_ips", lambda host: ("203.0.113.9",) if host == "b.example.com" else ())
    submitted: list[str] = []
    ctl._zapret_dns_pool = lambda: SimpleNamespace(submit=lambda fn, host: submitted.append(host))

    AppController._prefetch_zapret_server_ips(ctl)

    assert submitted == ["a.example.com", "c.example.com"]
