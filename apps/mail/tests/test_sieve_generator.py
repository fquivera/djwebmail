"""Unit tests for Sieve code generation and parsing (RFC 5228)."""

from __future__ import annotations

from apps.mail.services.sieve_generator import (
    FilterAction,
    FilterCondition,
    FilterRule,
    rules_to_sieve_script,
    sieve_script_to_rules,
)


def test_empty_rules_produces_valid_empty_sieve_script():
    script = rules_to_sieve_script([])
    assert "DjWebmail Sieve Filter Script" in script
    assert "require" not in script
    parsed = sieve_script_to_rules(script)
    assert parsed == []


def test_compile_single_rule_with_fileinto_and_stop():
    rule = FilterRule(
        name="Archive Invoices",
        active=True,
        conjunction="allof",
        conditions=[
            FilterCondition(field="subject", comparator="contains", value="Invoice"),
            FilterCondition(field="from", comparator="contains", value="billing@example.com"),
        ],
        actions=[
            FilterAction(action_type="fileinto", argument="Invoices"),
            FilterAction(action_type="mark_read"),
        ],
        stop=True,
    )

    script = rules_to_sieve_script([rule])
    assert 'require ["fileinto", "imap4flags"];' in script
    assert 'header :contains "Subject" "Invoice"' in script
    assert 'header :contains "From" "billing@example.com"' in script
    assert 'fileinto "Invoices";' in script
    assert 'addflag "\\Seen";' in script
    assert "stop;" in script

    # Verify lossless round-trip parse
    parsed_rules = sieve_script_to_rules(script)
    assert len(parsed_rules) == 1
    p = parsed_rules[0]
    assert p.name == "Archive Invoices"
    assert p.active is True
    assert p.conjunction == "allof"
    assert len(p.conditions) == 2
    assert p.conditions[0].field == "subject"
    assert p.conditions[0].value == "Invoice"
    assert len(p.actions) == 2
    assert p.actions[0].action_type == "fileinto"
    assert p.actions[0].argument == "Invoices"
    assert p.actions[1].action_type == "mark_read"
    assert p.stop is True


def test_compile_rule_with_or_conjunction_and_discard():
    rule = FilterRule(
        name="Drop Spam",
        active=True,
        conjunction="anyof",
        conditions=[
            FilterCondition(field="subject", comparator="is", value="Casino"),
            FilterCondition(field="from", comparator="ends_with", value="spam.net"),
        ],
        actions=[
            FilterAction(action_type="discard"),
        ],
        stop=True,
    )

    script = rules_to_sieve_script([rule])
    assert "anyof (" in script
    assert 'header :is "Subject" "Casino"' in script
    assert 'header :matches "From" "*spam.net"' in script
    assert "discard;" in script
    assert "stop;" in script


def test_inactive_rule_is_commented_out():
    rule = FilterRule(
        name="Disabled Rule",
        active=False,
        conditions=[FilterCondition(field="subject", value="Promo")],
        actions=[FilterAction(action_type="fileinto", argument="Promos")],
    )

    script = rules_to_sieve_script([rule])
    assert "# Rule 'Disabled Rule' is disabled" in script
    assert "fileinto" not in script or 'require ["fileinto"]' not in script


def test_parse_external_sieve_script_without_metadata():
    external_script = """
    require ["fileinto"];

    # rule:[Move Notifications]
    if header :contains "From" "notifications@github.com" {
        fileinto "GitHub";
        stop;
    }
    """

    rules = sieve_script_to_rules(external_script)
    assert len(rules) == 1
    r = rules[0]
    assert r.name == "Move Notifications"
    assert len(r.conditions) == 1
    assert r.conditions[0].field == "from"
    assert r.conditions[0].value == "notifications@github.com"
    assert len(r.actions) == 1
    assert r.actions[0].action_type == "fileinto"
    assert r.actions[0].argument == "GitHub"
    assert r.stop is True
