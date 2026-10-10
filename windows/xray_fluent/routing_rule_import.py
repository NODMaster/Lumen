from __future__ import annotations

import ipaddress
import json
import re
from typing import Any
from urllib.parse import urlsplit

try:
    import yaml
except ImportError:  # pragma: no cover - optional in source-only environments
    yaml = None


_ACTIONS = {
    "direct": "direct",
    "freedom": "direct",
    "proxy": "proxy",
    "vpn": "proxy",
    "reject": "block",
    "block": "block",
    "blocked": "block",
    "blackhole": "block",
}


def _action(value: Any) -> str:
    normalized = str(value or "proxy").strip().lower()
    return _ACTIONS.get(normalized, "proxy")


def _append(result: list[tuple[str, str]], address: Any, action: Any) -> None:
    value = str(address or "").strip()
    if value:
        result.append((value, _action(action)))


def _parse_clash_rule(value: str) -> tuple[str, str] | None:
    parts = [part.strip() for part in value.split(",")]
    if len(parts) < 2:
        return None
    kind = parts[0].upper()
    action = parts[2] if len(parts) >= 3 else "proxy"
    target = parts[1]
    prefixes = {
        "DOMAIN": "full:",
        "DOMAIN-SUFFIX": "domain:",
        "DOMAIN-KEYWORD": "keyword:",
        "DOMAIN-REGEX": "regexp:",
        "GEOSITE": "geosite:",
        "GEOIP": "geoip:",
    }
    if kind in prefixes:
        return f"{prefixes[kind]}{target}", _action(action)
    if kind in {"IP-CIDR", "IP-CIDR6"}:
        return target, _action(action)
    return None


def _parse_rule_object(value: dict[str, Any], result: list[tuple[str, str]]) -> None:
    action = value.get("action") or value.get("outboundTag") or value.get("outbound")
    for key in ("address", "domain", "domains", "ip", "ips"):
        addresses = value.get(key)
        if isinstance(addresses, str):
            _append(result, addresses, action)
        elif isinstance(addresses, list):
            for address in addresses:
                _append(result, address, action)


def _parse_structured(payload: Any) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, str):
                parsed = _parse_clash_rule(item)
                if parsed:
                    result.append(parsed)
                else:
                    _append(result, item, "proxy")
            elif isinstance(item, dict):
                _parse_rule_object(item, result)
        return result
    if not isinstance(payload, dict):
        return result

    for key, action in (("direct", "direct"), ("proxy", "proxy"), ("block", "block")):
        values = payload.get(key)
        if isinstance(values, list):
            for value in values:
                _append(result, value, action)

    rules = payload.get("rules")
    if rules is None and isinstance(payload.get("routing"), dict):
        rules = payload["routing"].get("rules")
    if isinstance(rules, list):
        result.extend(_parse_structured(rules))
    return result


def parse_routing_rules(text: str, *, suffix: str = "") -> list[tuple[str, str]]:
    source = str(text or "").strip()
    if not source:
        return []

    extension = suffix.strip().lower()
    structured: Any = None
    if extension == ".json" or source[:1] in {"{", "["}:
        try:
            structured = json.loads(source)
        except (TypeError, ValueError):
            if extension == ".json":
                raise ValueError("Некорректный JSON-файл правил") from None
    elif extension in {".yaml", ".yml"}:
        if yaml is None:
            raise ValueError("Для импорта YAML требуется PyYAML")
        try:
            structured = yaml.safe_load(source)
        except Exception as exc:
            raise ValueError(f"Некорректный YAML-файл правил: {exc}") from exc

    if structured is not None:
        return _parse_structured(structured)

    result: list[tuple[str, str]] = []
    for raw_line in source.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(("#", ";")):
            continue
        if "|" in line:
            address, _, action = line.partition("|")
            _append(result, address, action)
            continue
        clash = _parse_clash_rule(line)
        if clash:
            result.append(clash)
        else:
            _append(result, line, "proxy")
    return result


# ── Normalisation of hand-typed addresses ───────────────────────────────
# Users paste whole URLs ("https://www.example.com:8443/path?q"), add a port
# or a trailing dot; routing needs the bare host, IP or CIDR.

_PASSTHROUGH_PREFIXES = ("keyword:", "regexp:", "geosite:", "geoip:", "ext:", "ext-domain:", "ext-ip:")
_HOST_PREFIXES = ("domain:", "full:")
_LABEL_RE = re.compile(r"^(?!-)[a-z0-9_-]{1,63}(?<!-)$")
_SPLIT_RE = re.compile(r"[\s,;]+")


def _normalize_ip(value: str) -> str | None:
    value = value.strip()
    if not value:
        return None
    try:
        if "/" in value:
            return str(ipaddress.ip_network(value, strict=False))
        return str(ipaddress.ip_address(value))
    except ValueError:
        return None


def _extract_host(value: str) -> str:
    text = value.strip()
    if "://" in text or text.startswith("//"):
        try:
            netloc = urlsplit(text if "://" in text else "http:" + text).netloc
        except ValueError:
            return ""
    else:
        netloc = re.split(r"[/?#]", text, maxsplit=1)[0]
    netloc = netloc.rsplit("@", 1)[-1].strip()
    if netloc.startswith("["):
        end = netloc.find("]")
        return netloc[1:end] if end > 0 else ""
    if netloc.count(":") == 1:
        netloc = netloc.partition(":")[0]
    return netloc.strip()


def _normalize_host(value: str, *, allow_mask: bool = True, strip_www: bool = True) -> str | None:
    host = value.strip().lower().rstrip(".")
    mask = ""
    if allow_mask and host.startswith("*."):
        mask, host = "*.", host[2:]
    elif allow_mask and host.startswith("."):
        mask, host = "*.", host[1:]
    if not host:
        return None
    try:
        host = host.encode("idna").decode("ascii").lower()
    except UnicodeError:
        return None
    labels = host.split(".")
    if len(labels) < 2 or not all(_LABEL_RE.match(label) for label in labels):
        return None
    if labels[-1].isdigit():
        # Looks like a broken IPv4 address (e.g. 10.0.0.300).
        return None
    if strip_www and not mask and labels[0] == "www" and len(labels) > 2:
        host = ".".join(labels[1:])
    return mask + host


def normalize_routing_address(value: Any) -> str | None:
    """Bare domain / mask / IP / CIDR for a hand-typed rule, None if invalid.

    URLs lose scheme, credentials, port, path, query and fragment; hosts are
    lower-cased, IDN is converted to punycode, a leading ``www.`` and a
    trailing dot are dropped. ``domain:``/``full:`` keep their prefix with a
    normalised host; ``keyword:``/``regexp:``/``geosite:``/``geoip:``/``ext:``
    rules are kept as typed.
    """
    text = str(value or "").strip().strip("'\"<>")
    if not text:
        return None
    lower = text.lower()
    for prefix in _PASSTHROUGH_PREFIXES:
        if lower.startswith(prefix):
            rest = text[len(prefix):].strip()
            return f"{prefix}{rest}" if rest else None
    for prefix in _HOST_PREFIXES:
        if lower.startswith(prefix):
            host = _extract_host(text[len(prefix):])
            normalized = _normalize_host(host, allow_mask=False, strip_www=False) if host else None
            return f"{prefix}{normalized}" if normalized else None
    ip = _normalize_ip(text)
    if ip:
        return ip
    host = _extract_host(text)
    if not host:
        return None
    return _normalize_ip(host) or _normalize_host(host)


def split_routing_addresses(text: Any) -> list[str]:
    """Several addresses typed in one field (commas, spaces or new lines)."""
    source = str(text or "").strip()
    if not source:
        return []
    if source.lower().startswith("regexp:"):
        return [source]
    return [item for item in _SPLIT_RE.split(source) if item]
