"""Tests for the non-LLM candidate-matter grouping pre-filter."""

from pathlib import Path

from app.services.matter_grouping import (
    extract_numeric_tokens,
    group_by_shared_tokens,
    group_tokens,
    min_token_digits_for_principle,
)


def test_extract_numeric_tokens_finds_five_plus_digit_runs() -> None:
    tokens = extract_numeric_tokens("Vertrag 999888777, Zähler 1ABC0012345678, Az. 1122334455, kurz 1234")

    assert "999888777" in tokens
    assert "1122334455" in tokens
    assert "1234" not in tokens  # below the 5-digit floor


def test_pertinence_lowers_the_token_floor_to_four_digits() -> None:
    text = "kurz 1234 lang 999888"
    assert "1234" not in extract_numeric_tokens(text)  # provenance default
    assert "1234" in extract_numeric_tokens(text, min_digits=4)  # pertinence


def test_min_token_digits_for_principle_maps_the_two_principles() -> None:
    assert min_token_digits_for_principle("provenance") == 5
    assert min_token_digits_for_principle("pertinence") == 4


def test_pertinence_forms_a_group_a_conservative_run_would_miss() -> None:
    digests = {
        Path("a.md"): "customer 1234",
        Path("b.md"): "ref 1234 again",
    }
    assert group_by_shared_tokens(digests) == []  # 4-digit token ignored at default floor
    groups = group_by_shared_tokens(digests, min_digits=4)
    assert len(groups) == 1


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


def test_alphanumeric_reference_token_forms_a_group() -> None:
    digests = {
        Path("insurances/social.md"): "Identifiers: versicherungsnummer: 13040393S105",
        Path("work/employment.md"): "Identifiers: versicherungsnummer: 13040393S105",
        Path("unrelated.md"): "Identifiers: kundennummer: 999888777",
    }

    groups = group_by_shared_tokens(digests)

    assert len(groups) == 1
    assert set(groups[0]) == {Path("insurances/social.md"), Path("work/employment.md")}
    assert "13040393S105" in extract_numeric_tokens(digests[Path("insurances/social.md")])


def test_shared_year_alone_does_not_form_a_group() -> None:
    # A bare calendar year must never merge two unrelated folders into one matter.
    digests = {
        Path("a.md"): "Summary: events in 2023 about ACME",
        Path("b.md"): "Summary: events in 2023 about Beta Corp",
    }

    groups = group_by_shared_tokens(digests, min_digits=4)

    assert groups == []
    assert "2023" not in extract_numeric_tokens("events in 2023", min_digits=4)
