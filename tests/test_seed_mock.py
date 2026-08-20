from datetime import date

import pytest

from scripts.seed_mock import _month_starts, generate_synthetic_rows


def test_synthetic_generator_is_deterministic_and_splits_all_rows():
    first = generate_synthetic_rows(101, date(2026, 1, 1), date(2026, 1, 31), seed=42)
    second = generate_synthetic_rows(101, date(2026, 1, 1), date(2026, 1, 31), seed=42)

    assert first == second
    assert {bank: len(rows) for bank, rows in first.items()} == {"BIDV": 15, "MB": 72, "VPB": 14}
    assert sum(map(len, first.values())) == 101

    for rows in first.values():
        assert len({row.ref_no for row in rows}) == len(rows)
        assert all(date(2026, 1, 1) <= row.posted_at.date() <= date(2026, 1, 31) for row in rows)
        assert all(row.signed_amount and abs(row.signed_amount) % 1_000 == 0 for row in rows)
        assert all(row.category_name for row in rows)


def test_synthetic_generator_changes_with_seed_and_validates_arguments():
    first = generate_synthetic_rows(10, seed=1)
    second = generate_synthetic_rows(10, seed=2)
    assert first != second

    with pytest.raises(ValueError):
        generate_synthetic_rows(-1)
    with pytest.raises(ValueError):
        generate_synthetic_rows(1, date(2026, 2, 1), date(2026, 1, 1))


def test_month_starts_cross_year_boundary():
    assert list(_month_starts(date(2025, 11, 20), date(2026, 2, 3))) == [
        date(2025, 11, 1), date(2025, 12, 1), date(2026, 1, 1), date(2026, 2, 1),
    ]
