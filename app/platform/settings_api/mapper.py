"""Map app.core.settings.SettingSpec → React SettingsFieldMeta shape."""

from __future__ import annotations

import re
from typing import Any

from app.core import settings as runtime_settings
from app.core.settings import SettingSpec


def section_slug(section_title: str) -> str:
    """Stable id for nav/save — ASCII slug from Vietnamese/English titles."""
    s = section_title.strip().lower()
    # lightweight VN diacritics strip for stable ids
    replacements = {
        "à": "a",
        "á": "a",
        "ả": "a",
        "ã": "a",
        "ạ": "a",
        "ă": "a",
        "ằ": "a",
        "ắ": "a",
        "ẳ": "a",
        "ẵ": "a",
        "ặ": "a",
        "â": "a",
        "ầ": "a",
        "ấ": "a",
        "ẩ": "a",
        "ẫ": "a",
        "ậ": "a",
        "è": "e",
        "é": "e",
        "ẻ": "e",
        "ẽ": "e",
        "ẹ": "e",
        "ê": "e",
        "ề": "e",
        "ế": "e",
        "ể": "e",
        "ễ": "e",
        "ệ": "e",
        "ì": "i",
        "í": "i",
        "ỉ": "i",
        "ĩ": "i",
        "ị": "i",
        "ò": "o",
        "ó": "o",
        "ỏ": "o",
        "õ": "o",
        "ọ": "o",
        "ô": "o",
        "ồ": "o",
        "ố": "o",
        "ổ": "o",
        "ỗ": "o",
        "ộ": "o",
        "ơ": "o",
        "ờ": "o",
        "ớ": "o",
        "ở": "o",
        "ỡ": "o",
        "ợ": "o",
        "ù": "u",
        "ú": "u",
        "ủ": "u",
        "ũ": "u",
        "ụ": "u",
        "ư": "u",
        "ừ": "u",
        "ứ": "u",
        "ử": "u",
        "ữ": "u",
        "ự": "u",
        "ỳ": "y",
        "ý": "y",
        "ỷ": "y",
        "ỹ": "y",
        "ỵ": "y",
        "đ": "d",
        "&": " and ",
    }
    for a, b in replacements.items():
        s = s.replace(a, b)
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    return s or "general"


def _unit_for_react(spec: SettingSpec) -> str | None:
    if not spec.unit:
        return None
    u = spec.unit.strip().lower()
    if u in ("giây", "sec", "s", "second", "seconds"):
        return "s"
    if u in ("phút", "min", "minute", "minutes"):
        return "min"
    if u in ("ms", "millisecond", "milliseconds"):
        return "ms"
    return spec.unit


def _type_for_react(spec: SettingSpec) -> str:
    if spec.is_secret:
        return "secret"
    if spec.type == "bool":
        return "boolean"
    if spec.type == "int":
        key = spec.key.upper()
        if key.endswith("_MS"):
            return "duration_ms"
        if key.endswith("_MINUTES") or (spec.unit or "").lower() in ("phút", "min"):
            return "minutes"
        if key.endswith("_SEC") or (spec.unit or "").lower() in ("giây", "s", "sec"):
            return "duration_s"
        return "integer"
    if spec.type == "float":
        return "float"
    if spec.type == "enum":
        return "string"  # React select later; string is safe
    # URLs / paths
    key_u = spec.key.upper()
    if "URL" in key_u or key_u.endswith("_BASE") or key_u.endswith("_ENDPOINT"):
        return "url"
    return "string"


def _pair_role(spec: SettingSpec, all_specs: dict[str, SettingSpec]) -> tuple[str | None, str | None, str | None]:
    """Return (groupId, pairedRole, groupLabel)."""
    if spec.pair_with:
        return spec.key + "__pair", "min", spec.title
    # secondary of a pair?
    for other in all_specs.values():
        if other.pair_with == spec.key:
            return other.key + "__pair", "max", other.title
    return None, None, None


def spec_to_field_meta(spec: SettingSpec, all_specs: dict[str, SettingSpec]) -> dict[str, Any]:
    group_id, paired_role, group_label = _pair_role(spec, all_specs)
    rules: dict[str, Any] = {}
    if spec.min is not None:
        rules["min"] = float(spec.min) if spec.type == "float" else int(spec.min)
    if spec.max is not None:
        rules["max"] = float(spec.max) if spec.type == "float" else int(spec.max)
    if spec.is_secret or spec.keep_blank:
        # required false — empty means keep
        pass
    else:
        # non-secret optional unless bool (always has value)
        pass

    meta: dict[str, Any] = {
        "key": spec.key,
        "label": spec.title,
        "description": spec.description or "",
        "section": section_slug(spec.section),
        "sectionLabel": spec.section,
        "subsection": None,
        "type": _type_for_react(spec),
        "unit": _unit_for_react(spec),
        "placeholder": "",
        "defaultValue": spec.default_getter(),
        "required": False,
        "secret": bool(spec.is_secret),
        "envLocked": bool(spec.env_only),
        "restartRequired": bool(spec.restart_required),
        "validationRules": rules or None,
        "testAction": None,
        "dangerLevel": "low",
        "groupId": group_id,
        "pairedRole": paired_role,
        "groupLabel": group_label if paired_role == "min" else None,
    }
    # TikWM test action
    if spec.key == "TIKWM_API_BASE":
        meta["testAction"] = {
            "id": "tikwm_ping",
            "label": "Test connection",
            "dependsOnKeys": ["TIKWM_API_BASE", "TIKWM_API_TIMEOUT_SEC"],
        }
    return meta


def list_field_metas() -> list[dict[str, Any]]:
    specs = {
        k: s
        for k, s in runtime_settings.SETTINGS.items()
        if not runtime_settings.is_studio_only(s)
    }
    fields = [spec_to_field_meta(s, specs) for s in specs.values()]
    # stable-ish: section label then title
    fields.sort(key=lambda f: (f["sectionLabel"].lower(), f["label"].lower()))
    return fields


def build_values_payload(db) -> dict[str, Any]:
    overrides = runtime_settings.get_overrides(db, use_cache=False)
    values: dict[str, Any] = {}
    sources: dict[str, str] = {}
    secrets: dict[str, dict[str, bool]] = {}

    for key, spec in runtime_settings.SETTINGS.items():
        if runtime_settings.is_studio_only(spec):
            continue
        has_override = key in overrides
        sources[key] = runtime_settings.resolve_setting_source(spec, has_override)
        if spec.is_secret:
            effective = overrides.get(key, spec.default_getter())
            has_value = bool(str(effective or "").strip())
            secrets[key] = {"hasValue": has_value}
            # never send secret plaintext
            continue
        values[key] = runtime_settings.get_effective(db, key)

    return {"values": values, "sources": sources, "secrets": secrets}
