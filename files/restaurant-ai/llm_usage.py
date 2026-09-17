"""Observed Anthropic usage, separate from the historical uncached cost field.

First-party Claude API, standard global pricing; no currency conversion.
Verified 2026-09-17: https://platform.claude.com/docs/en/about-claude/pricing
Unknown models and absent usage remain unpriced rather than using a fallback rate.
"""
from decimal import Decimal

PRICING_VERSION = "anthropic-global-standard-2026-09-17"
PRICING_SOURCE = "https://platform.claude.com/docs/en/about-claude/pricing"
# USD / million tokens: input, output, 5m write, 1h write, cache read.
RATES = {
    "claude-sonnet-4-6": ("3", "15", "3.75", "6", "0.30"),
    "claude-sonnet-4-5": ("3", "15", "3.75", "6", "0.30"),
    "claude-haiku-4-5": ("1", "5", "1.25", "2", "0.10"),
}


def _get(value, key, default=None):
    return value.get(key, default) if isinstance(value, dict) else getattr(value, key, default)


def observed_call(response) -> dict:
    """Use response.model and usage; this caller explicitly uses default 5m caching."""
    model = _get(response, "model")
    usage = _get(response, "usage")
    rate_key = next((name for name in RATES if model == name or
                     (isinstance(model, str) and model.startswith(name + "-")
                      and model[len(name) + 1:].isdigit())), None)
    names = ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
    counts = {name: _get(usage, name) for name in names}
    valid = usage is not None and all(
        value is None or (isinstance(value, int) and not isinstance(value, bool) and value >= 0)
        for value in counts.values()
    ) and counts["input_tokens"] is not None and counts["output_tokens"] is not None
    # Cache counters can be absent in older SDKs; do not silently label those costs complete.
    cache_observed = all(counts[name] is not None for name in names[2:])
    creation = _get(usage, "cache_creation")
    write_5m = _get(creation, "ephemeral_5m_input_tokens")
    write_1h = _get(creation, "ephemeral_1h_input_tokens")
    if creation is None:
        write_5m, write_1h = counts["cache_creation_input_tokens"], 0
    else:
        write_5m, write_1h = write_5m or 0, write_1h or 0
        valid = valid and write_5m + write_1h == counts["cache_creation_input_tokens"]
    complete = valid and cache_observed and rate_key is not None
    components = None
    if complete:
        values = (counts["input_tokens"], counts["output_tokens"], write_5m, write_1h, counts["cache_read_input_tokens"])
        components = dict(zip(("input", "output", "cache_write_5m", "cache_write_1h", "cache_read"),
            [str(Decimal(value) * Decimal(rate) / 1_000_000) for value, rate in zip(values, RATES[rate_key])]))
    return {
        "model": model, "usage": counts, "cache_write_5m_tokens": write_5m,
        "cache_write_1h_tokens": write_1h, "cost_components_usd": components,
        "cost_usd": str(sum(map(Decimal, components.values()))) if components else None,
        "pricing_version": PRICING_VERSION if rate_key else None,
        "status": "complete" if complete else "unknown_model" if rate_key is None else "incomplete_usage",
    }


def metric_cost_fields(calls: list[dict]) -> dict:
    """No per-call rounding; retain exact component decimals in usage_json."""
    complete = bool(calls) and all(call["status"] == "complete" for call in calls)
    fields = {
        "modelo_observado": ",".join(sorted({call["model"] for call in calls if call.get("model")})) or None,
        "usage_json": calls,
        "tokens_cache_creation": sum(call["usage"].get("cache_creation_input_tokens") or 0 for call in calls),
        "tokens_cache_read": sum(call["usage"].get("cache_read_input_tokens") or 0 for call in calls),
        "tokens_cache_write_5m": sum(call.get("cache_write_5m_tokens") or 0 for call in calls),
        "tokens_cache_write_1h": sum(call.get("cache_write_1h_tokens") or 0 for call in calls),
        "tarifa_versao": PRICING_VERSION if complete else None,
        "custo_status": "complete" if complete else "incomplete_usage_or_model",
    }
    components = ("input", "output", "cache_write_5m", "cache_write_1h", "cache_read")
    for component in components:
        fields[f"custo_{component}_usd"] = (sum(Decimal(call["cost_components_usd"][component]) for call in calls)
                                             if complete else None)
    fields["custo_total_usd"] = sum(Decimal(call["cost_usd"]) for call in calls) if complete else None
    return fields
