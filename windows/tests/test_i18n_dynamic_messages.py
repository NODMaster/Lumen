from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from xray_fluent import i18n

ROOT = Path(__file__).resolve().parents[1]
LOCALES = ROOT / "xray_fluent" / "locales"
I18N_QML = ROOT / "xray_fluent" / "qml_app" / "qml" / "I18n.qml"
CYRILLIC = re.compile(r"[\u0400-\u04FF]")
PLACEHOLDER = re.compile(r"\{(\w+)\}")

# Complete backend messages as they are rendered by workers/controllers.
BACKEND_MESSAGES = (
    "Подключено: Server 1",
    "Сначала откройте зашифрованный профиль",
    "Сервер подписки отклонил соединение. Попробуйте включить «Загружать подписки через прокси/TUN» в Настройки → Подписки.",
    "SOCKS порт 1080 уже занят процессом nekoray.exe (PID 42). Измените SOCKS порт в настройках или закройте конфликтующее приложение.",
    "Порт 2080 уже занят другим процессом.",
    "Нельзя включить Discord Voice одновременно с другим VPN/прокси-клиентом: другой VPN/прокси-клиент. Отключите или закройте его.",
    "Xray завершился неожиданно с кодом -1 (CrashExit).",
    "Ошибка синтаксиса JSON: Expecting value (строка 3, столбец 5)\n  x\n    ^",
    "Не удалось восстановить state.json. Файл сохранён как state.bad.json. broken",
    "Тест скорости остановлен (3/10)",
    "Релиз v1.2.3 найден, но установщик не содержит SHA-256",
    "Подписка истекает: 3 дн.",
    "[zapret] Запуск: default.txt (12 аргументов напрямую)",
    "Закройте конфликтующее приложение или нажмите «Сменить порт». bind: address already in use",
)


def _catalog(language: str) -> dict[str, str]:
    data = json.loads((LOCALES / f"{language}.json").read_text(encoding="utf-8"))
    return {key: value for key, value in data.items() if not key.startswith("__")}


def test_catalogs_share_keys_and_placeholders() -> None:
    catalogs = {language: _catalog(language) for language in ("en", "fa", "zh")}
    assert set(catalogs["en"]) == set(catalogs["fa"]) == set(catalogs["zh"])
    for key in catalogs["en"]:
        expected = sorted(set(PLACEHOLDER.findall(key)))
        for language, catalog in catalogs.items():
            assert sorted(set(PLACEHOLDER.findall(catalog[key]))) == expected, (language, key)


@pytest.mark.parametrize("language", ["en", "fa", "zh"])
def test_backend_messages_are_fully_translated(language: str) -> None:
    catalog = i18n.CATALOGS[language]
    for message in BACKEND_MESSAGES:
        translated = i18n.translate_dynamic(message, catalog)
        assert translated is not None, message
        assert not CYRILLIC.search(translated), (message, translated)


def test_nested_values_are_translated_recursively() -> None:
    translated = i18n.translate_dynamic(BACKEND_MESSAGES[3], i18n.CATALOGS["en"])
    assert translated == (
        "SOCKS port 1080 is already used by process nekoray.exe (PID 42). "
        "Change the SOCKS port in settings or close the conflicting app."
    )


def test_formatting_helpers_do_not_match_arbitrary_messages() -> None:
    # "{secs}с" is a duration helper; it must not turn unrelated text into "...s".
    assert i18n.translate_dynamic("Неизвестный процесс", i18n.CATALOGS["en"]) is None
    assert i18n.translate_dynamic("Plain English text", i18n.CATALOGS["en"]) is None


def test_log_model_localizes_humanized_entries() -> None:
    from PyQt6.QtCore import QCoreApplication

    from xray_fluent.qml_app.bridge.log_model import LogModel

    app = QCoreApplication.instance() or QCoreApplication([])
    assert app is not None
    catalog = i18n.CATALOGS["en"]
    model = LogModel(translator=lambda text: i18n.translate_dynamic(text, catalog) or text)
    model.append_line("[proxy] failed to listen on port 1080: address already in use")
    entry = model.entry_at(0)
    assert entry is not None
    assert entry.message == "Local port 1080 is already used by another program."
    assert entry.details.startswith("Close the conflicting app or click “Change port”.")
    assert entry.source == "Proxy"
    assert entry.action_label == "Change port"
    assert "local port 1080" in entry.search_text


_QML_SCRIPT = textwrap.dedent(
    r"""
    import json, os, shutil, sys, tempfile
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtCore import QObject, QUrl, pyqtProperty, pyqtSignal
    from PyQt6.QtGui import QGuiApplication
    from PyQt6.QtQml import QQmlComponent, QQmlEngine, qmlRegisterSingletonInstance

    locales, i18n_qml, language, messages = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]

    class App(QObject):
        changed = pyqtSignal()
        def __init__(self):
            super().__init__()
            with open(os.path.join(locales, language + ".json"), encoding="utf-8") as fh:
                self._map = {k: v for k, v in json.load(fh).items() if not k.startswith("__")}
        @pyqtProperty(str, notify=changed)
        def language(self):
            return language
        @pyqtProperty("QVariantMap", notify=changed)
        def translations(self):
            return self._map

    app = QGuiApplication(sys.argv[:1])
    mock = App()
    qmlRegisterSingletonInstance("App", 1, 0, "App", mock)
    root = tempfile.mkdtemp()
    try:
        module = os.path.join(root, "LumenI18n")
        os.makedirs(module)
        shutil.copy(i18n_qml, os.path.join(module, "I18n.qml"))
        with open(os.path.join(module, "qmldir"), "w", encoding="utf-8") as fh:
            fh.write("module LumenI18n\nsingleton I18n 1.0 I18n.qml\n")
        engine = QQmlEngine()
        engine.addImportPath(root)
        source = (
            "import QtQuick\nimport LumenI18n 1.0\n"
            "QtObject { property var out: (function() { var items = " + messages + "; var r = []; "
            "for (var i = 0; i < items.length; ++i) r.push(I18n.t(items[i])); return r; })() }"
        )
        component = QQmlComponent(engine)
        component.setData(source.encode("utf-8"), QUrl.fromLocalFile(os.path.join(root, "probe.qml")))
        obj = component.create()
        assert obj is not None, component.errorString()
        sys.stdout.reconfigure(encoding="utf-8")
        print(json.dumps(obj.property("out").toVariant(), ensure_ascii=True))
    finally:
        shutil.rmtree(root, ignore_errors=True)
    """
)


@pytest.mark.parametrize("language", ["en", "zh"])
def test_qml_i18n_translates_rendered_backend_messages(language: str) -> None:
    pytest.importorskip("PyQt6.QtQml")
    messages = list(BACKEND_MESSAGES) + ["Настройки", "Plain English text"]
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen", QT_QUICK_BACKEND="software")
    fixture_argv = ["fixture", str(LOCALES), str(I18N_QML), language, json.dumps(messages, ensure_ascii=True)]
    code = "import sys\nsys.argv = " + repr(fixture_argv) + "\n" + _QML_SCRIPT
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "run_safe_tests.py"),
            "--exec-fixture",
            base64.b64encode(code.encode("utf-8")).decode("ascii"),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=60,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    output = json.loads(completed.stdout.strip().splitlines()[-1])
    python_side = [i18n.translate_dynamic(message, i18n.CATALOGS[language]) for message in messages]
    assert output[:-1] == python_side[:-1]
    assert output[-1] == "Plain English text"
    assert not any(CYRILLIC.search(text) for text in output)
