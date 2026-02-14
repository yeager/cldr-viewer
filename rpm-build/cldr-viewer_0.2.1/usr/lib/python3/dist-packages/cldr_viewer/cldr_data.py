"""CLDR JSON data fetching and caching."""

import json
import os
import time
import urllib.request
import urllib.error
from pathlib import Path

CACHE_DIR = Path.home() / ".cache" / "cldr-viewer"
CACHE_TTL = 86400  # 24 hours

CLDR_BASE = "https://raw.githubusercontent.com/unicode-org/cldr-json/main/cldr-json"

# Map of category → (package, sub-path-template with {locale})
CLDR_PACKAGES = {
    "dates": ("cldr-dates-full", "main/{locale}/ca-gregorian.json"),
    "dateFields": ("cldr-dates-full", "main/{locale}/dateFields.json"),
    "currencies": ("cldr-numbers-full", "main/{locale}/currencies.json"),
    "units": ("cldr-units-full", "main/{locale}/units.json"),
    "timeZoneNames": ("cldr-dates-full", "main/{locale}/timeZoneNames.json"),
    "languages": ("cldr-localenames-full", "main/{locale}/languages.json"),
    "territories": ("cldr-localenames-full", "main/{locale}/territories.json"),
}

AVAILABLE_LOCALES_URL = (
    f"{CLDR_BASE}/cldr-dates-full/availableLocales.json"
)


def _ensure_cache_dir():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _cache_path(url: str) -> Path:
    import hashlib
    h = hashlib.sha256(url.encode()).hexdigest()[:16]
    return CACHE_DIR / f"{h}.json"


def _fetch_json(url: str) -> dict | None:
    _ensure_cache_dir()
    cp = _cache_path(url)
    if cp.exists():
        age = time.time() - cp.stat().st_mtime
        if age < CACHE_TTL:
            with open(cp) as f:
                return json.load(f)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "cldr-viewer/0.1"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        with open(cp, "w") as f:
            json.dump(data, f)
        return data
    except (urllib.error.URLError, json.JSONDecodeError, OSError):
        # Return stale cache if available
        if cp.exists():
            with open(cp) as f:
                return json.load(f)
        return None


def get_available_locales() -> list[str]:
    """Return list of available locale codes."""
    data = _fetch_json(AVAILABLE_LOCALES_URL)
    if data and "availableLocales" in data:
        locales = data["availableLocales"].get("full", [])
        return sorted(locales)
    return ["en", "sv"]


def get_category_data(locale: str, category: str) -> dict:
    """Fetch CLDR data for a locale and category. Returns nested dict."""
    if category not in CLDR_PACKAGES:
        return {}
    pkg, path_tpl = CLDR_PACKAGES[category]
    path = path_tpl.format(locale=locale)
    url = f"{CLDR_BASE}/{pkg}/{path}"
    data = _fetch_json(url)
    if not data:
        return {}
    return data


def flatten_dict(d: dict, prefix: str = "") -> dict[str, str]:
    """Flatten nested dict to dotted-key → value pairs."""
    result = {}
    for k, v in d.items():
        key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            result.update(flatten_dict(v, key))
        else:
            result[key] = str(v) if v is not None else ""
    return result


def get_flat_category(locale: str, category: str) -> dict[str, str]:
    """Get flattened key→value data for a locale/category."""
    raw = get_category_data(locale, category)
    return flatten_dict(raw)


def compute_coverage(locale: str, ref_locale: str = "en") -> dict[str, dict]:
    """Compute coverage for each category vs a reference locale.

    Returns {category: {"total": N, "present": N, "missing": N, "percent": float, "missing_keys": [...]}}
    """
    result = {}
    for cat in CLDR_PACKAGES:
        ref = get_flat_category(ref_locale, cat)
        loc = get_flat_category(locale, cat)
        ref_keys = set(ref.keys())
        loc_keys = set(loc.keys())
        present = ref_keys & loc_keys
        # Also count keys with empty values as missing
        empty = {k for k in present if not loc.get(k, "").strip()}
        actual_present = len(present) - len(empty)
        missing_keys = sorted((ref_keys - loc_keys) | empty)
        total = len(ref_keys) if ref_keys else 1
        result[cat] = {
            "total": len(ref_keys),
            "present": actual_present,
            "missing": len(missing_keys),
            "percent": round(actual_present / total * 100, 1) if total else 100.0,
            "missing_keys": missing_keys,
        }
    return result


def clear_cache():
    """Remove all cached files."""
    if CACHE_DIR.exists():
        for f in CACHE_DIR.iterdir():
            f.unlink(missing_ok=True)
