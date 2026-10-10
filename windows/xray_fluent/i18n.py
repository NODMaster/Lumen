from __future__ import annotations

import json
import re
from pathlib import Path

_PLACEHOLDER = re.compile(r"\{(\w+)\}")
_LOCALES_DIR = Path(__file__).resolve().parent / "locales"

SOURCE_LANGUAGE = "ru"
_FALLBACK_NAMES = {"ru": "Русский", "en": "English"}

CATALOGS: dict[str, dict[str, str]] = {}
LANGUAGE_NAMES: dict[str, str] = {}


def _load_catalogs() -> None:
    CATALOGS.clear()
    LANGUAGE_NAMES.clear()
    LANGUAGE_NAMES[SOURCE_LANGUAGE] = _FALLBACK_NAMES[SOURCE_LANGUAGE]
    if not _LOCALES_DIR.is_dir():
        return
    for path in sorted(_LOCALES_DIR.glob("*.json")):
        code = path.stem.lower()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        name = data.get("__name__")
        CATALOGS[code] = {
            key: value
            for key, value in data.items()
            if isinstance(key, str) and not key.startswith("__")
        }
        LANGUAGE_NAMES[code] = name if isinstance(name, str) and name else _FALLBACK_NAMES.get(code, code.upper())


_load_catalogs()

_language = "en" if "en" in CATALOGS else SOURCE_LANGUAGE


def available_languages() -> list[str]:
    return [SOURCE_LANGUAGE] + sorted(CATALOGS)


def language_name(code: str) -> str:
    return LANGUAGE_NAMES.get(code, code.upper())


def set_language(lang: str) -> str:
    global _language
    candidate = (lang or "").lower()
    if candidate in available_languages():
        _language = candidate
    elif "en" in CATALOGS:
        _language = "en"
    else:
        _language = SOURCE_LANGUAGE
    return _language


def get_language() -> str:
    return _language


def active_map() -> dict:
    if _language == SOURCE_LANGUAGE:
        return {}
    return CATALOGS.get(_language, {})


def translate(_key: str, params: dict | None = None) -> str:
    text = active_map().get(_key, _key)
    if params:
        def _sub(match):
            name = match.group(1)
            return str(params[name]) if name in params else match.group(0)
        text = _PLACEHOLDER.sub(_sub, text)
    return text


_CYRILLIC = re.compile(r"[\u0400-\u04FF]")
_LETTER = re.compile(r"[^\W\d_]")
_MIN_TEMPLATE_LETTERS = 3
_TEMPLATE_CACHE: dict[int, tuple[dict[str, str], int, list[tuple[re.Pattern[str], list[str], str]]]] = {}


def _compiled_templates(translations: dict[str, str]) -> list[tuple[re.Pattern[str], list[str], str]]:
    """Return ``(pattern, field_names, source)`` for usable catalog templates.

    Templates are tried from the longest source to the shortest so specific
    messages win over generic ones.  Templates whose literal text has fewer
    than three letters (for example ``{secs}с``) are formatting helpers, not
    messages; matching them against arbitrary text would mistranslate it.
    """
    cached = _TEMPLATE_CACHE.get(id(translations))
    if cached is not None and cached[0] is translations and cached[1] == len(translations):
        return cached[2]
    compiled: list[tuple[re.Pattern[str], list[str], str]] = []
    for source in sorted(
        (key for key in translations if _PLACEHOLDER.search(key)),
        key=len,
        reverse=True,
    ):
        parts = _PLACEHOLDER.split(source)
        literal = "".join(parts[0::2])
        if len(_LETTER.findall(literal)) < _MIN_TEMPLATE_LETTERS:
            continue
        field_names: list[str] = []
        pattern_parts: list[str] = []
        for index, part in enumerate(parts):
            if index % 2:
                field_index = len(field_names)
                field_names.append(part)
                pattern_parts.append(f"(?P<_field_{field_index}>.*?)")
            else:
                pattern_parts.append(re.escape(part))
        compiled.append((re.compile("".join(pattern_parts), flags=re.DOTALL), field_names, source))
    _TEMPLATE_CACHE[id(translations)] = (translations, len(translations), compiled)
    return compiled


def translate_dynamic(
    message: str,
    catalog: dict[str, str] | None = None,
    _depth: int = 0,
) -> str | None:
    """Translate a rendered message by matching catalog keys with placeholders.

    Backend workers report complete Russian messages such as
    ``sing-box актуален (1.2.3)``.  Regular key lookup cannot translate those
    once the version has already been inserted, so match them against catalog
    templates such as ``sing-box актуален ({version})``.  Captured values that
    are themselves known Russian messages (for example a hint appended to an
    error) are translated recursively.
    """
    translations = active_map() if catalog is None else catalog
    if not message or not translations:
        return None
    exact = translations.get(message)
    if exact is not None:
        return exact
    if not _CYRILLIC.search(message):
        return None

    for pattern, field_names, source in _compiled_templates(translations):
        match = pattern.fullmatch(message)
        if match is None:
            continue
        params: dict[str, str] = {}
        for index, name in enumerate(field_names):
            value = match.group(f"_field_{index}")
            if _depth < 2 and value and _CYRILLIC.search(value):
                localized_value = translate_dynamic(value, translations, _depth + 1)
                if localized_value is not None:
                    value = localized_value
            params.setdefault(name, value)
        translated = translations[source]
        return _PLACEHOLDER.sub(
            lambda placeholder: params.get(placeholder.group(1), placeholder.group(0)),
            translated,
        )
    return None


def tr(_key: str, **params) -> str:
    return translate(_key, params)
