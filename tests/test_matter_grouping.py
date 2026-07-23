"""Tests for the non-LLM candidate-matter grouping pre-filter."""

from pathlib import Path

from app.services.matter_grouping import extract_numeric_tokens, group_by_shared_tokens, group_tokens


def test_extract_numeric_tokens_finds_five_plus_digit_runs() -> None:
    tokens = extract_numeric_tokens("Vertrag 999888777, Zähler 1ABC0012345678, Az. 1122334455, kurz 1234")

    assert "999888777" in tokens
    assert "1122334455" in tokens
    assert "1234" not in tokens  # below the 5-digit floor


def test_two_aggregates_sharing_a_token_form_one_group() -> None:
    digests = {
        Path("providers/eon.md"): "Sources: contract_999888777.pdf",
        Path("finances/statement.md"): "Summary: payment ref 999888777 to ACME",
        Path("health/visit.md"): "Summary: dentist appointment",
    }

    groups = group_by_shared_tokens(digests)

    assert len(groups) == 1
    assert set(groups[0]) == {Path("providers/eon.md"), Path("finances/statement.md")}


def test_singleton_aggregates_excluded_from_groups() -> None:
    digests = {
        Path("a.md"): "no shared numbers here, just 42",
        Path("b.md"): "also nothing, just 99",
    }

    groups = group_by_shared_tokens(digests)

    assert groups == []


def test_chained_tokens_merge_into_one_group_via_union_find() -> None:
    # A-B share token1, B-C share token2 (different token) -> one group {A, B, C}.
    digests = {
        Path("a.md"): "ref 111111",
        Path("b.md"): "ref 111111 and also 222222",
        Path("c.md"): "ref 222222",
    }

    groups = group_by_shared_tokens(digests)

    assert len(groups) == 1
    assert set(groups[0]) == {Path("a.md"), Path("b.md"), Path("c.md")}


def test_unrelated_pair_and_related_pair_form_separate_groups() -> None:
    digests = {
        Path("a.md"): "ref 111111",
        Path("b.md"): "ref 111111",
        Path("c.md"): "ref 999999",
        Path("d.md"): "ref 999999",
    }

    groups = group_by_shared_tokens(digests)

    assert len(groups) == 2
    grouped_sets = {frozenset(g) for g in groups}
    assert frozenset({Path("a.md"), Path("b.md")}) in grouped_sets
    assert frozenset({Path("c.md"), Path("d.md")}) in grouped_sets


def test_group_tokens_returns_the_shared_token() -> None:
    digests = {
        Path("providers/eon.md"): "Sources: contract_999888777.pdf",
        Path("finances/statement.md"): "Summary: payment ref 999888777 to ACME",
    }

    tokens = group_tokens([Path("providers/eon.md"), Path("finances/statement.md")], digests)

    assert tokens == ["999888777"]


def test_group_tokens_includes_both_tokens_in_a_chained_group() -> None:
    # Same chain as test_chained_tokens_merge_into_one_group_via_union_find: both tokens
    # link at least two members of the group, so a naming slug should reflect both.
    digests = {
        Path("a.md"): "ref 111111",
        Path("b.md"): "ref 111111 and also 222222",
        Path("c.md"): "ref 222222",
    }

    tokens = group_tokens([Path("a.md"), Path("b.md"), Path("c.md")], digests)

    assert tokens == ["111111", "222222"]
