"""Sieve (RFC 5228) code generation, parsing, and rule definitions.

Converts structured Carbonio-style filter rules (conditions and actions) to
standard RFC 5228 Sieve scripts executed by mail delivery agents (Dovecot Pigeonhole),
and parses scripts back into editable structured rules.
"""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from typing import Any

SIEVE_METADATA_PREFIX = "# DJWEBMAIL_FILTER_RULES_V1: "

# Sieve field identifier mappings
HEADER_FIELD_MAP = {
    "subject": "Subject",
    "from": "From",
    "to": "To",
    "cc": "Cc",
    "to_or_cc": ["To", "Cc"],
    "reply_to": "Reply-To",
    "sender": "Sender",
}


@dataclass
class FilterCondition:
    """A single matching condition in a filter rule."""

    field: str = "subject"  # "subject", "from", "to", "cc", "size"
    comparator: str = "contains"  # "contains", "not_contains", "is", "starts_with", etc.
    value: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FilterCondition:
        return cls(
            field=str(data.get("field", "subject")),
            comparator=str(data.get("comparator", "contains")),
            value=str(data.get("value", "")),
        )


@dataclass
class FilterAction:
    """An action to execute when rule conditions match."""

    action_type: str = "keep"  # "keep", "fileinto", "discard", "redirect", "mark_read", etc.
    argument: str = ""  # Destination folder name or target email address

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FilterAction:
        return cls(
            action_type=str(data.get("action_type", "keep")),
            argument=str(data.get("argument", "")),
        )


@dataclass
class FilterRule:
    """A complete structured filter rule inspired by Zextras Carbonio."""

    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = ""
    active: bool = True
    conjunction: str = "anyof"  # "anyof" (OR) or "allof" (AND)
    conditions: list[FilterCondition] = field(default_factory=list)
    actions: list[FilterAction] = field(default_factory=list)
    stop: bool = True  # Stop processing further rules ("No procesar filtros adicionales")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "active": self.active,
            "conjunction": self.conjunction,
            "conditions": [c.to_dict() for c in self.conditions],
            "actions": [a.to_dict() for a in self.actions],
            "stop": self.stop,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FilterRule:
        rule_id = str(data.get("id") or str(uuid.uuid4())[:8])
        name = str(data.get("name", ""))
        active = bool(data.get("active", True))
        conjunction = "allof" if data.get("conjunction") == "allof" else "anyof"
        raw_conds = data.get("conditions") or []
        conditions = [FilterCondition.from_dict(c) for c in raw_conds if isinstance(c, dict)]
        raw_acts = data.get("actions") or []
        actions = [FilterAction.from_dict(a) for a in raw_acts if isinstance(a, dict)]
        stop = bool(data.get("stop", True))
        return cls(
            id=rule_id,
            name=name,
            active=active,
            conjunction=conjunction,
            conditions=conditions,
            actions=actions,
            stop=stop,
        )


def escape_sieve_string(val: str) -> str:
    """Escape special characters for standard Sieve double-quoted string literals."""
    return val.replace("\\", "\\\\").replace('"', '\\"')


def compile_condition(cond: FilterCondition) -> str:
    """Compile a FilterCondition into a Sieve test expression."""
    field_id = cond.field.strip().lower()
    comp = cond.comparator.strip().lower()
    val = cond.value.strip()

    if field_id == "size":
        # e.g. size :over 10M or size :under 500K
        size_comp = ":under" if comp in {"less_than", "under", "not_contains"} else ":over"
        return f"size {size_comp} {escape_sieve_string(val or '1M')}"

    header_names = HEADER_FIELD_MAP.get(field_id, "Subject")
    if isinstance(header_names, list):
        formatted_headers = "[" + ", ".join(f'"{h}"' for h in header_names) + "]"
    else:
        formatted_headers = f'"{header_names}"'

    escaped_val = escape_sieve_string(val)

    if comp == "is":
        return f'header :is {formatted_headers} "{escaped_val}"'
    elif comp == "not_is":
        return f'not header :is {formatted_headers} "{escaped_val}"'
    elif comp == "starts_with":
        return f'header :matches {formatted_headers} "{escaped_val}*"'
    elif comp == "ends_with":
        return f'header :matches {formatted_headers} "*{escaped_val}"'
    elif comp == "not_contains":
        return f'not header :contains {formatted_headers} "{escaped_val}"'
    else:  # default "contains"
        return f'header :contains {formatted_headers} "{escaped_val}"'


def compile_action(act: FilterAction) -> tuple[str, set[str]]:
    """Compile a FilterAction into a Sieve action statement and needed capabilities."""
    kind = act.action_type.strip().lower()
    arg = act.argument.strip()
    escaped_arg = escape_sieve_string(arg)

    if kind == "fileinto":
        return f'fileinto "{escaped_arg}";', {"fileinto"}
    elif kind == "discard":
        return "discard;", set()
    elif kind == "redirect":
        return f'redirect "{escaped_arg}";', set()
    elif kind == "mark_read":
        return 'addflag "\\Seen";', {"imap4flags"}
    elif kind == "mark_starred":
        return 'addflag "\\Flagged";', {"imap4flags"}
    else:  # default "keep"
        return "keep;", set()


def compile_rule_to_sieve(rule: FilterRule) -> tuple[str, set[str]]:
    """Compile a single FilterRule into a Sieve conditional block."""
    if not rule.active:
        return f"# Rule '{escape_sieve_string(rule.name)}' is disabled\n", set()

    capabilities: set[str] = set()
    tests: list[str] = []

    for cond in rule.conditions:
        if cond.value or cond.field == "size":
            tests.append(compile_condition(cond))

    if not tests:
        tests.append('header :contains "Subject" ""')

    if len(tests) == 1:
        condition_clause = tests[0]
    else:
        conjunction = "allof" if rule.conjunction == "allof" else "anyof"
        joined_tests = ",\n        ".join(tests)
        condition_clause = f"{conjunction} (\n        {joined_tests}\n    )"

    action_lines: list[str] = []
    for act in rule.actions:
        statement, required_caps = compile_action(act)
        capabilities.update(required_caps)
        action_lines.append(f"    {statement}")

    if rule.stop:
        action_lines.append("    stop;")

    if not action_lines:
        action_lines.append("    keep;")

    actions_block = "\n".join(action_lines)

    rule_title = rule.name or rule.id
    code = (
        f"# rule:[{escape_sieve_string(rule_title)}]\n"
        f"if {condition_clause} {{\n{actions_block}\n}}\n"
    )
    return code, capabilities


def rules_to_sieve_script(
    rules: Sequence[FilterRule],
    *,
    script_name: str = "djwebmail",
) -> str:
    """Compile a list of structured FilterRules into a complete RFC 5228 Sieve script.

    Embeds JSON metadata as a comment line to ensure lossless round-trip reconstruction
    in the Carbonio-style visual webmail editor.
    """
    rule_blocks: list[str] = []
    all_capabilities: set[str] = set()

    for rule in rules:
        block, caps = compile_rule_to_sieve(rule)
        rule_blocks.append(block)
        all_capabilities.update(caps)

    # Encode metadata for visual editor fidelity
    rules_dict = [r.to_dict() for r in rules]
    metadata_json = json.dumps(
        {"name": script_name, "rules": rules_dict},
        ensure_ascii=False,
    )
    metadata_comment = f"{SIEVE_METADATA_PREFIX}{metadata_json}\n"

    lines: list[str] = [
        "# DjWebmail Sieve Filter Script (RFC 5228)",
        "# Generated automatically. Managed via Webmail Settings.",
        metadata_comment,
    ]

    if all_capabilities:
        sorted_caps = sorted(all_capabilities)
        req_str = ", ".join(f'"{c}"' for c in sorted_caps)
        lines.append(f"require [{req_str}];\n")

    lines.extend(rule_blocks)
    return "\n".join(lines).strip() + "\n"


def sieve_script_to_rules(script_source: str) -> list[FilterRule]:
    """Parse a Sieve script into structured FilterRules.

    Prefers lossless JSON metadata if present; falls back to pattern-matching
    standard Sieve syntax for externally generated scripts.
    """
    if not script_source:
        return []

    # 1. Check for DjWebmail metadata comment
    for line in script_source.splitlines():
        line = line.strip()
        if line.startswith(SIEVE_METADATA_PREFIX):
            json_part = line[len(SIEVE_METADATA_PREFIX) :].strip()
            try:
                payload = json.loads(json_part)
                raw_rules = payload.get("rules", [])
                return [FilterRule.from_dict(r) for r in raw_rules if isinstance(r, dict)]
            except Exception:
                pass

    # 2. Fallback parser: extract standard Sieve `if ... { ... }` blocks
    rules: list[FilterRule] = []
    rule_matches = re.finditer(
        r"(?:#\s*rule:\[(?P<name>[^\]]+)\]\s*)?if\s+(?P<cond>.*?)\s*\{(?P<actions>.*?)\}",
        script_source,
        re.DOTALL,
    )

    for i, match in enumerate(rule_matches, start=1):
        name = match.group("name") or f"Rule {i}"
        raw_cond = match.group("cond")
        raw_actions = match.group("actions")

        conjunction = "allof" if "allof" in raw_cond else "anyof"
        conditions: list[FilterCondition] = []

        # Find header contains/is/matches tests
        test_matches = re.finditer(
            r'(?P<not>not\s+)?header\s+:(?P<comp>contains|is|matches)\s+(?:"(?P<hdr>[^"]+)"|\[(?P<hdrs>[^\]]+)\])\s+"(?P<val>[^"]*)"',
            raw_cond,
            re.IGNORECASE,
        )
        for tm in test_matches:
            hdr = tm.group("hdr") or "Subject"
            comp_type = tm.group("comp").lower()
            is_negated = bool(tm.group("not"))
            val = tm.group("val")

            if comp_type == "is":
                comp = "not_is" if is_negated else "is"
            elif comp_type == "matches":
                if val.startswith("*") and not val.endswith("*"):
                    comp = "ends_with"
                    val = val[1:]
                elif val.endswith("*") and not val.startswith("*"):
                    comp = "starts_with"
                    val = val[:-1]
                else:
                    comp = "contains"
            else:
                comp = "not_contains" if is_negated else "contains"

            field_name = hdr.lower().replace("-", "_")
            conditions.append(FilterCondition(field=field_name, comparator=comp, value=val))

        actions: list[FilterAction] = []
        for line in raw_actions.splitlines():
            line = line.strip()
            fileinto_m = re.match(r'fileinto\s+"(?P<folder>[^"]+)";', line, re.IGNORECASE)
            if fileinto_m:
                actions.append(
                    FilterAction(action_type="fileinto", argument=fileinto_m.group("folder"))
                )
            elif "discard;" in line.lower():
                actions.append(FilterAction(action_type="discard"))
            elif "addflag" in line.lower() and "seen" in line.lower():
                actions.append(FilterAction(action_type="mark_read"))
            elif "addflag" in line.lower() and "flagged" in line.lower():
                actions.append(FilterAction(action_type="mark_starred"))
            elif "keep;" in line.lower():
                actions.append(FilterAction(action_type="keep"))
            elif "redirect" in line.lower():
                redir_m = re.match(r'redirect\s+"(?P<to>[^"]+)";', line, re.IGNORECASE)
                if redir_m:
                    actions.append(
                        FilterAction(action_type="redirect", argument=redir_m.group("to"))
                    )

        stop = "stop;" in raw_actions.lower()
        rules.append(
            FilterRule(
                id=str(uuid.uuid4())[:8],
                name=name,
                active=True,
                conjunction=conjunction,
                conditions=conditions,
                actions=actions or [FilterAction(action_type="keep")],
                stop=stop,
            )
        )

    return rules
