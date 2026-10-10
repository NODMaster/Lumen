from __future__ import annotations

import xml.etree.ElementTree as ET

from xray_fluent import startup
from xray_fluent.qml_app import tray

NS = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}


def _task(command: str = '"C:\\Program Files\\Lumen\\Lumen.exe" --tray') -> ET.Element:
    text = startup.build_startup_task_xml(command, "PC\\user")
    return ET.fromstring(text.split("\n", 1)[1])


def _value(root: ET.Element, path: str) -> str:
    node = root.find(path, NS)
    assert node is not None, path
    return node.text or ""


def test_task_has_no_battery_time_or_priority_limits() -> None:
    root = _task()
    assert _value(root, "t:Settings/t:DisallowStartIfOnBatteries") == "false"
    assert _value(root, "t:Settings/t:StopIfGoingOnBatteries") == "false"
    assert _value(root, "t:Settings/t:ExecutionTimeLimit") == "PT0S"
    assert int(_value(root, "t:Settings/t:Priority")) <= 6
    assert _value(root, "t:Settings/t:MultipleInstancesPolicy") == "IgnoreNew"


def test_task_starts_tray_launch_for_current_user_elevated() -> None:
    root = _task()
    assert _value(root, "t:Triggers/t:LogonTrigger/t:UserId") == "PC\\user"
    assert _value(root, "t:Principals/t:Principal/t:UserId") == "PC\\user"
    assert _value(root, "t:Principals/t:Principal/t:LogonType") == "InteractiveToken"
    assert _value(root, "t:Principals/t:Principal/t:RunLevel") == "HighestAvailable"
    assert _value(root, "t:Actions/t:Exec/t:Command") == "C:\\Program Files\\Lumen\\Lumen.exe"
    assert _value(root, "t:Actions/t:Exec/t:Arguments") == "--tray"
    assert _value(root, "t:Actions/t:Exec/t:WorkingDirectory") == "C:\\Program Files\\Lumen"


def test_task_xml_escapes_paths() -> None:
    root = _task('"D:\\R&D <x>\\Lumen.exe"')
    assert _value(root, "t:Actions/t:Exec/t:Command") == "D:\\R&D <x>\\Lumen.exe"
    assert root.find("t:Actions/t:Exec/t:Arguments", NS) is None


def test_create_task_uses_xml_and_falls_back(monkeypatch) -> None:
    calls: list[list[str]] = []
    timeouts: list[object] = []

    class _Result:
        def __init__(self, code: int) -> None:
            self.returncode = code

    def _run(command, **kwargs):
        calls.append(list(command))
        timeouts.append(kwargs.get("timeout"))
        return _Result(1 if "/XML" in command else 0)

    monkeypatch.setattr(startup, "_delete_startup_task", lambda: None)
    monkeypatch.setattr(startup, "_current_task_user", lambda: "PC\\user")
    monkeypatch.setattr(startup.subprocess, "run", _run)
    startup._create_startup_task('"C:\\Lumen\\Lumen.exe" --tray')
    assert "/XML" in calls[0]
    assert "/SC" in calls[1] and "ONLOGON" in calls[1]
    assert all(value == startup.SCHTASKS_TIMEOUT for value in timeouts)


def test_create_task_stops_after_xml_success(monkeypatch) -> None:
    calls: list[list[str]] = []

    class _Result:
        returncode = 0

    monkeypatch.setattr(startup, "_delete_startup_task", lambda: None)
    monkeypatch.setattr(startup, "_current_task_user", lambda: "PC\\user")
    monkeypatch.setattr(startup.subprocess, "run", lambda command, **_kw: calls.append(list(command)) or _Result())
    startup._create_startup_task('"C:\\Lumen\\Lumen.exe" --tray')
    assert len(calls) == 1 and "/XML" in calls[0]


def test_tray_waits_for_taskbar_before_reinstalling_icon(monkeypatch) -> None:
    present = iter([False, True])
    monkeypatch.setattr(tray, "_taskbar_present", lambda: next(present))
    scheduled: list[int] = []
    monkeypatch.setattr(tray.QTimer, "singleShot", staticmethod(lambda ms, _cb: scheduled.append(ms)))

    class _Timer:
        stopped = False

        def stop(self) -> None:
            self.stopped = True

    holder = type("Holder", (), {})()
    holder._taskbar_timer = _Timer()
    holder._taskbar_wait_ticks = 0
    holder._reinstall_tray_icon = lambda: None
    tray.QmlTray._wait_for_taskbar(holder)
    assert not holder._taskbar_timer.stopped and scheduled == []
    tray.QmlTray._wait_for_taskbar(holder)
    assert holder._taskbar_timer.stopped and scheduled == [1500, 6000]
