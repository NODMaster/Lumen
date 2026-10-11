from __future__ import annotations

import json
import subprocess
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

import xray_fluent.engines.singbox.manager as m
from xray_fluent.engines.singbox.manager import SingBoxManager

CONFIG = {
    "inbounds": [{"type": "mixed", "tag": "mixed-in", "listen": "127.0.0.1", "listen_port": 2080}],
    "outbounds": [{"type": "direct", "tag": "direct"}],
}
SHELL = Path(r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe")


def _done(code: int = 0, out: bytes = b"", err: bytes = b"") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess([], code, out, err)


def _write_script(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# hook\n", encoding="utf-8")


@pytest.fixture
def hook(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"
    state = SimpleNamespace(
        user=tmp_path / "data" / "custom" / m.PRE_LAUNCH_SCRIPT_NAME,
        install=tmp_path / "app" / "custom" / m.PRE_LAUNCH_SCRIPT_NAME,
        tmp=tmp_path,
        calls=[],
        runner=lambda command: _done(),
        logs=[],
    )
    monkeypatch.setattr(m, "CUSTOM_PRE_LAUNCH_SCRIPT", state.user)
    monkeypatch.setattr(m, "INSTALL_PRE_LAUNCH_SCRIPT", state.install)
    monkeypatch.setattr(m, "RUNTIME_DIR", runtime)
    monkeypatch.setattr(m, "PRE_LAUNCH_CONFIG_FILE", runtime / "singbox_config.pre_launch.json")
    monkeypatch.setattr(m, "SINGBOX_CONFIG_FILE", runtime / "singbox_config.json")
    monkeypatch.setattr(m, "_powershell_executable", lambda: SHELL)

    def run(command, **kwargs):
        state.calls.append((list(command), kwargs))
        return state.runner(list(command))

    monkeypatch.setattr(m, "run_text_pumped", run)
    state.manager = SingBoxManager()
    state.manager.log_received.connect(state.logs.append)
    return state


def _edit_port(port: int, encoding: str = "utf-8"):
    def runner(command):
        path = Path(command[-1])
        data = json.loads(path.read_text(encoding="utf-8"))
        data["inbounds"][0]["listen_port"] = port
        path.write_text(json.dumps(data), encoding=encoding)
        return _done(0, "готово\r\n".encode("cp866"))

    return runner


def test_missing_script_is_a_no_op(hook) -> None:
    assert hook.manager._apply_pre_launch_script(deepcopy(CONFIG)) is None
    assert hook.calls == []


def test_script_edits_a_copy_with_absolute_powershell(hook) -> None:
    _write_script(hook.user)
    hook.runner = _edit_port(2090, encoding="utf-16")  # Windows PowerShell Out-File default
    original = deepcopy(CONFIG)
    edited = hook.manager._apply_pre_launch_script(original)
    assert edited is not None and edited["inbounds"][0]["listen_port"] == 2090
    assert original == CONFIG
    command, kwargs = hook.calls[0]
    assert command[0] == str(SHELL)
    assert command[command.index("-File") + 1] == str(hook.user)
    assert kwargs["timeout"] == m.PRE_LAUNCH_TIMEOUT_SEC
    assert not m.PRE_LAUNCH_CONFIG_FILE.exists()
    assert "[pre-launch] готово" in hook.logs


def test_script_next_to_lumen_is_used(hook) -> None:
    _write_script(hook.install)
    hook.runner = _edit_port(2091)
    edited = hook.manager._apply_pre_launch_script(deepcopy(CONFIG))
    assert edited is not None and edited["inbounds"][0]["listen_port"] == 2091
    command = hook.calls[0][0]
    assert command[command.index("-File") + 1] == str(hook.install)


def test_data_folder_script_wins_over_the_one_next_to_lumen(hook) -> None:
    _write_script(hook.user)
    _write_script(hook.install)
    hook.runner = _edit_port(2092)
    assert hook.manager._apply_pre_launch_script(deepcopy(CONFIG)) is not None
    command = hook.calls[0][0]
    assert command[command.index("-File") + 1] == str(hook.user)


def test_failed_script_keeps_the_original_config(hook) -> None:
    _write_script(hook.user)
    hook.runner = lambda command: _done(2, b"", b"boom")
    assert hook.manager._apply_pre_launch_script(deepcopy(CONFIG)) is None
    assert "[pre-launch][err] boom" in hook.logs
    assert any("exited with code 2" in line for line in hook.logs)
    assert not m.PRE_LAUNCH_CONFIG_FILE.exists()


def test_invalid_json_keeps_the_original_config(hook) -> None:
    _write_script(hook.user)

    def runner(command):
        Path(command[-1]).write_text("{broken", encoding="utf-8")
        return _done()

    hook.runner = runner
    assert hook.manager._apply_pre_launch_script(deepcopy(CONFIG)) is None
    assert any("invalid JSON" in line for line in hook.logs)


def test_timeout_keeps_the_original_config(hook) -> None:
    _write_script(hook.user)

    def runner(command):
        raise subprocess.TimeoutExpired(command, m.PRE_LAUNCH_TIMEOUT_SEC)

    hook.runner = runner
    assert hook.manager._apply_pre_launch_script(deepcopy(CONFIG)) is None
    assert any("did not finish" in line for line in hook.logs)
    assert not m.PRE_LAUNCH_CONFIG_FILE.exists()


def test_missing_powershell_is_reported(hook, monkeypatch) -> None:
    monkeypatch.setattr(m, "_powershell_executable", lambda: None)
    _write_script(hook.user)
    assert hook.manager._apply_pre_launch_script(deepcopy(CONFIG)) is None
    assert hook.calls == []
    assert any("PowerShell not found" in line for line in hook.logs)


def _start_until_launch(hook, monkeypatch, edited, valid):
    exe = hook.tmp / "sing-box.exe"
    exe.write_bytes(b"")
    validated: list[dict] = []
    monkeypatch.setattr(m, "resolve_configured_path", lambda *_args, **_kwargs: exe)
    monkeypatch.setattr(SingBoxManager, "_apply_pre_launch_script", lambda self, cfg: deepcopy(edited))
    monkeypatch.setattr(
        SingBoxManager,
        "validate_config",
        lambda self, _path, cfg: (validated.append(deepcopy(cfg)) or (valid, "" if valid else "bad field")),
    )
    monkeypatch.setattr(SingBoxManager, "_wait_clash_api_port_released", lambda self: None)

    def blocked_popen(*_args, **_kwargs):
        raise OSError("process start blocked in test")

    monkeypatch.setattr(m.subprocess, "Popen", blocked_popen)
    assert hook.manager.start(str(exe), deepcopy(CONFIG), prevalidated=True) is False
    written = json.loads(m.SINGBOX_CONFIG_FILE.read_text(encoding="utf-8"))
    return validated, written


def test_start_validates_and_runs_the_edited_config(hook, monkeypatch) -> None:
    edited = deepcopy(CONFIG)
    edited["inbounds"][0]["listen_port"] = 2090
    validated, written = _start_until_launch(hook, monkeypatch, edited, True)
    assert [cfg["inbounds"][0]["listen_port"] for cfg in validated] == [2090]
    assert written["inbounds"][0]["listen_port"] == 2090
    assert any("proxy ports=[2090]" in line or "2090" in line for line in hook.logs if "startup attempt" in line)


def test_start_falls_back_when_sing_box_rejects_the_edit(hook, monkeypatch) -> None:
    edited = deepcopy(CONFIG)
    edited["inbounds"][0]["listen_port"] = 2090
    validated, written = _start_until_launch(hook, monkeypatch, edited, False)
    assert validated and validated[0]["inbounds"][0]["listen_port"] == 2090
    assert written["inbounds"][0]["listen_port"] == 2080
    assert any("rejected the edited config: bad field" in line for line in hook.logs)
