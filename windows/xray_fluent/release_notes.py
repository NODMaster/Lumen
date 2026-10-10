"""Curated "What's new" notes shown by the welcome flow after an update.

Titles and texts are Russian source strings; QML translates them through
``I18n.t`` so every note needs matching keys in ``locales/*.json``.  Add an
entry for every released ``APP_VERSION`` (tests enforce this).
"""

from __future__ import annotations

import re
from typing import Any

# Saved profiles written before Lumen tracked the welcome flow have no
# ``onboarding_version``.  They are upgrades, never fresh installs.
LEGACY_PROFILE_VERSION = "0"

_VERSION_RE = re.compile(r"^v?(\d+(?:\.\d+){0,3})(?:[-+].*)?$")

# glyph: Segoe Fluent Icons code point rendered next to the note.
RELEASE_NOTES: dict[str, tuple[dict[str, str], ...]] = {
    "2.0.0": (
        {
            "glyph": "\uE8BC",
            "title": "Приветствие и «Что нового»",
            "text": "Новый мастер первого запуска: язык, тема, регион, маршрутизация и серверы за пару минут. После каждого обновления Lumen коротко расскажет, что изменилось.",
        },
        {
            "glyph": "\uE753",
            "title": "Бесплатный WARP в один клик",
            "text": "Lumen сам получает профили Cloudflare WARP — AmneziaWG и MASQUE — и добавляет их в группу «WARP». Без ботов и ручного копирования ключей.",
        },
        {
            "glyph": "\uE774",
            "title": "Полный перевод интерфейса",
            "text": "English, فارسی и 简体中文: переведены оставшиеся окна, подсказки, уведомления, журнал событий и сообщения об ошибках.",
        },
        {
            "glyph": "\uE7E8",
            "title": "Тихий автозапуск",
            "text": "При запуске вместе с Windows уже открытый Lumen остаётся в трее и не всплывает поверх других окон.",
        },
    ),
}

FALLBACK_NOTE: dict[str, str] = {
    "glyph": "\uE895",
    "title": "Исправления и улучшения",
    "text": "Lumen стал стабильнее и быстрее. Подробный список изменений — на странице релиза на GitHub.",
}


def version_key(value: Any) -> tuple[int, ...]:
    """Numeric release key; empty for unknown/invalid values."""
    match = _VERSION_RE.match(str(value or "").strip())
    if not match:
        return ()
    parts = [int(part) for part in match.group(1).split(".")]
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


def normalize_seen_version(value: Any) -> str:
    """Keep a saved onboarding version only when it is a plausible release."""
    text = str(value or "").strip().lstrip("v")
    if not text:
        return ""
    return text if version_key(text) else LEGACY_PROFILE_VERSION


def is_upgrade(seen_version: str, app_version: str) -> bool:
    """True when the profile last completed the flow on an older release."""
    seen = str(seen_version or "").strip()
    if not seen:
        return False  # fresh install: nothing to compare with
    current = version_key(app_version)
    previous = version_key(seen)
    if not current:
        return False
    return not previous or previous < current


def notes_between(seen_version: str, app_version: str, *, limit: int = 3) -> list[dict[str, Any]]:
    """Release groups newer than ``seen_version`` up to ``app_version`` (newest first)."""
    current_text = str(app_version or "").strip().lstrip("v")
    current = version_key(current_text)
    previous = version_key(seen_version) or (0, 0, 0)
    groups: list[dict[str, Any]] = []
    for version in sorted(RELEASE_NOTES, key=version_key, reverse=True):
        key = version_key(version)
        if key and previous < key <= current:
            groups.append({"version": version, "items": [dict(item) for item in RELEASE_NOTES[version]]})
    if current and (not groups or version_key(groups[0]["version"]) != current):
        groups.insert(0, {"version": current_text, "items": [dict(FALLBACK_NOTE)]})
    return groups[: max(1, int(limit))]


def release_note_strings() -> set[str]:
    """Every translatable string used by the notes (for catalog tests)."""
    strings = {FALLBACK_NOTE["title"], FALLBACK_NOTE["text"]}
    for items in RELEASE_NOTES.values():
        for item in items:
            strings.add(item["title"])
            strings.add(item["text"])
    return strings
