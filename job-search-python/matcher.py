"""
matcher.py — Computes how well a job's extracted attributes match the target rules.
"""

import re
from typing import Any


def _split_or_values(text: str) -> list[str]:
    """Split a target value on OR boundaries and return non-empty options."""
    return [part.strip() for part in re.split(r"\s+OR\s+", text, flags=re.IGNORECASE) if part.strip()]


def parse_exclusion_rules(exclusions: list[str]) -> tuple[list[dict[str, Any]], list[str]]:
    """
    Parse exclusion rules in the form: AttributeName=Value OR Value2

    Returns:
      - valid rule dicts
      - warnings for ignored invalid lines
    """
    rules: list[dict[str, Any]] = []
    warnings: list[str] = []

    for index, raw in enumerate(exclusions, start=1):
        line = raw.strip()
        if not line:
            continue
        if "=" not in line:
            warnings.append(
                f"Ignored exclusions line {index}: missing '=' ({line})"
            )
            continue

        attr_name, raw_value = line.split("=", 1)
        attr_name = attr_name.strip()
        raw_value = raw_value.strip()

        if not attr_name or not raw_value:
            warnings.append(
                f"Ignored exclusions line {index}: missing attribute name or value ({line})"
            )
            continue

        options = _split_or_values(raw_value)
        if not options:
            warnings.append(
                f"Ignored exclusions line {index}: no comparison values found ({line})"
            )
            continue

        rules.append(
            {
                "raw": line,
                "attribute": attr_name,
                "options": options,
            }
        )

    return rules, warnings


def apply_exclusions(
    extracted: dict[str, Any],
    exclusion_rules: list[dict[str, Any]],
) -> tuple[bool, list[dict[str, str]]]:
    """
    Evaluate exclusions against extracted attributes.

    Matching behavior:
      - Attribute title compare is case-insensitive exact match.
      - Value compare is case-insensitive and supports equals or contains.
      - OR values are supported in exclusion options.
    """
    if not exclusion_rules:
        return False, []

    attr_lookup = {str(name).strip().lower(): str(value) for name, value in extracted.items()}
    matched_details: list[dict[str, str]] = []

    for rule in exclusion_rules:
        rule_attr = str(rule.get("attribute", "")).strip()
        if not rule_attr:
            continue

        extracted_val = attr_lookup.get(rule_attr.lower())
        if extracted_val is None:
            continue

        extracted_lc = extracted_val.lower()
        for option in rule.get("options", []):
            option_lc = option.lower()
            if extracted_lc == option_lc or option_lc in extracted_lc:
                matched_details.append(
                    {
                        "rule": str(rule.get("raw", "")),
                        "attribute": rule_attr,
                        "matched_value": option,
                        "extracted": extracted_val,
                    }
                )
                break

    return bool(matched_details), matched_details


def _parse_salary_amount(text: str) -> int | None:
    """Parse a salary token like '$200K', '200,000', '200000' into an integer."""
    text = text.replace(",", "").replace("$", "").strip()
    match = re.match(r"(\d+(?:\.\d+)?)\s*([kK])?", text)
    if not match:
        return None
    value = float(match.group(1))
    if match.group(2):
        value *= 1000
    return int(value)


def _salary_range_includes(salary_attr: str, amount: int) -> bool:
    """
    Return True if the salary range string spans the given amount.
    Handles formats like:
      $100,000 - $200,000
      100K - 200K
      $150K–$250K
      Up to $300K
      $200,000+
    """
    if not salary_attr:
        return False

    # Try to pull two numbers (min and max)
    tokens = re.findall(r"\$?[\d,]+(?:\.\d+)?[kK]?", salary_attr)
    numbers = [_parse_salary_amount(t) for t in tokens if _parse_salary_amount(t) is not None]

    if len(numbers) >= 2:
        low, high = sorted(numbers[:2])
        return low <= amount <= high

    if len(numbers) == 1:
        single = numbers[0]
        # "$200K+" means >= 200K
        if "+" in salary_attr:
            return single <= amount
        # "Up to $300K" means <= 300K
        if re.search(r"up\s+to", salary_attr, re.IGNORECASE):
            return amount <= single
        # Single value — treat as exact
        return single == amount

    return False


def compute_match(
    extracted: dict[str, Any],
    targets: list[str],
) -> tuple[int, list[dict]]:
    """
    Returns (score_percent, details_list).

    Each item in details_list is:
        {"rule": str, "matched": bool, "extracted": str}
    """
    if not targets:
        return 100, []

    details = []
    for rule in targets:
        rule = rule.strip()
        if not rule or rule.startswith("#"):
            continue

        # Salary Range Includes <amount>
        includes_match = re.match(
            r"Salary\s+Range\s+Includes\s+(.+)", rule, re.IGNORECASE
        )
        if includes_match:
            raw_amount = includes_match.group(1).strip()
            amount = _parse_salary_amount(raw_amount)
            salary_val = extracted.get("Salary Range", "")
            matched = _salary_range_includes(salary_val, amount) if amount else False
            details.append({
                "rule":      rule,
                "matched":   matched,
                "extracted": salary_val or "(not found)",
            })
            continue

        # AttributeName=Value
        eq_match = re.match(r"^(.+?)=(.+)$", rule)
        if eq_match:
            attr_name  = eq_match.group(1).strip()
            target_val = eq_match.group(2).strip()
            extracted_val = extracted.get(attr_name, "")
            options = _split_or_values(target_val)
            matched = (
                any(option.lower() in extracted_val.lower() for option in options)
                if extracted_val
                else False
            )
            details.append({
                "rule":      rule,
                "matched":   matched,
                "extracted": extracted_val or "(not found)",
            })
            continue

        # Unrecognised rule — skip
        details.append({
            "rule":      rule,
            "matched":   False,
            "extracted": "(rule not understood)",
        })

    if not details:
        return 100, details

    matched_count = sum(1 for d in details if d["matched"])
    score = int(matched_count / len(details) * 100)
    return score, details
