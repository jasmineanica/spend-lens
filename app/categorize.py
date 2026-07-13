from __future__ import annotations

import yaml

from .config import DATA_DIR, get_settings

_UNCATEGORIZED = "Uncategorized"

with (DATA_DIR / "categories.yml").open(encoding="utf-8") as f:
    _CATS = yaml.safe_load(f)

with (DATA_DIR / "merchant_rules.yml").open(encoding="utf-8") as f:
    _RULES: list[dict] = yaml.safe_load(f)

BUCKETS: dict[str, list[str]] = _CATS["buckets"]
BUDGET: dict = _CATS["budget"]

# category -> bucket, and the flat ordered taxonomy of valid categories.
CATEGORY_TO_BUCKET: dict[str, str] = {
    cat: bucket for bucket, cats in BUCKETS.items() for cat in cats
}
TAXONOMY: list[str] = list(CATEGORY_TO_BUCKET.keys())


def bucket_for(category: str) -> str:
    return CATEGORY_TO_BUCKET.get(category, _UNCATEGORIZED)


def _match_rules(merchant: str, description: str = "") -> str | None:
    text = f"{merchant} {description}".lower()
    for rule in _RULES:
        for kw in rule["keywords"]:
            if kw.lower() in text:
                return rule["category"]
    return None


def _match_llm(merchant: str, description: str) -> str | None:
    """Local-only Claude fallback for unknown merchants. Returns None on any
    failure so categorization always degrades gracefully to Uncategorized."""
    settings = get_settings()
    if not settings.enable_llm or not settings.anthropic_api_key:
        return None
    try:
        import anthropic
    except ImportError:
        return None

    try:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        schema = {
            "type": "object",
            "properties": {
                "category": {"type": "string", "enum": TAXONOMY + [_UNCATEGORIZED]}
            },
            "required": ["category"],
        }
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            temperature=0.0,
            system=(
                "You categorize a single card transaction into exactly one of the "
                "provided budget categories. Only the merchant string is shared; no "
                "amounts or personal data. If nothing fits, choose 'Uncategorized'."
            ),
            messages=[{"role": "user", "content": f"Merchant: {merchant}\nMemo: {description}"}],
            tools=[{
                "name": "categorize",
                "description": "Assign the transaction to one budget category.",
                "input_schema": schema,
            }],
            tool_choice={"type": "tool", "name": "categorize"},
        )
        block = next(b for b in resp.content if b.type == "tool_use")
        category = block.input.get("category")
        return category if category in CATEGORY_TO_BUCKET else None
    except Exception:
        return None


def categorize(merchant: str, description: str = "") -> tuple[str, str]:
    """Return (category, bucket). Rules first, then optional local LLM fallback."""
    category = _match_rules(merchant, description)
    if category is None:
        category = _match_llm(merchant, description)
    if category is None:
        return _UNCATEGORIZED, _UNCATEGORIZED
    return category, bucket_for(category)
