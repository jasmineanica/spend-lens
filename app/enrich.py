from __future__ import annotations

import json
import re
from functools import lru_cache
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .config import get_settings

_UA = "SpendLens/1.0 (https://github.com/jasmineanica/spend-lens)"
_API = "https://www.wikidata.org/w/api.php"
_TIMEOUT = 1.2
_MAX_LIVE_LOOKUPS = 500  # per-process backstop so a huge import can't hammer Wikidata
_live_calls = 0

# Payment-processor prefixes that wrap the real merchant in a descriptor.
_PREFIXES = re.compile(r"^(sq|tst|sp|pp|paypal|ext|pos|dd|ch)\s*\*", re.IGNORECASE)


def _clean_merchant(raw: str) -> str:
    s = raw
    if "*" in s:
        s = _PREFIXES.sub("", s)
        s = s.split("*")[-1]
    s = re.sub(r"#?\d[\d\-]*", " ", s)      # drop store/order numbers
    s = re.sub(r"\s+", " ", s).strip(" -")
    return " ".join(s.split()[:3])          # keep the first few words


def _is_personish(merchant: str) -> bool:
    # Venmo person-to-person names have no useful public category.
    return "venmo -" in merchant.lower() or len(_clean_merchant(merchant)) < 3


def _category_from_text(text: str) -> str | None:
    from .categorize import _match_rules  # lazy import to avoid a cycle
    return _match_rules(text)


@lru_cache(maxsize=8192)
def _wikidata_descriptions(name: str) -> tuple[str, ...]:
    """Return short English descriptions of the top Wikidata matches for `name`
    (e.g. 'Starbucks' -> 'american coffeehouse chain'). Several are returned
    because an ambiguous name (e.g. 'Patagonia') may list a region before the
    company. Cached; fails soft to an empty tuple."""
    global _live_calls
    if _live_calls >= _MAX_LIVE_LOOKUPS:
        return ()
    _live_calls += 1
    try:
        url = _API + "?" + urlencode({
            "action": "wbsearchentities", "search": name, "language": "en",
            "uselang": "en", "format": "json", "limit": 6, "type": "item",
        })
        req = Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
        with urlopen(req, timeout=_TIMEOUT) as resp:
            data = json.load(resp)
        return tuple(
            (r.get("description") or "").lower()
            for r in (data.get("search") or []) if r.get("description")
        )
    except Exception:
        return ()


def enrich_category(merchant: str) -> str | None:
    """Map an unknown merchant to a taxonomy category via Wikidata. Returns None
    if disabled, if the merchant looks like a person, or if nothing maps."""
    if not get_settings().enable_enrich or _is_personish(merchant):
        return None
    name = _clean_merchant(merchant)
    if not name:
        return None
    for desc in _wikidata_descriptions(name):
        category = _category_from_text(f"{name} {desc}")
        if category:
            return category
    return None
