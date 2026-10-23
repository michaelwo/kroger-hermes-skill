from datetime import date
from pathlib import Path

from kroger_shopping.buysave_store import load_buysave_upcs, save_buysave


def test_round_trip_keeps_a_current_event(tmp_path: Path):
    save_buysave(
        tmp_path,
        offer_code="offer-1",
        description="Save $1 each when you buy 5 or more",
        end="2026-10-27",
        upcs=["2100061223", "0002100061223", ""],
    )
    assert load_buysave_upcs(tmp_path, today=date(2026, 10, 22)) == {"0002100061223"}


def test_expired_event_does_not_tag(tmp_path: Path):
    save_buysave(
        tmp_path,
        offer_code="offer-1",
        description="old",
        end="2026-10-21",
        upcs=["0002100061223"],
    )
    assert load_buysave_upcs(tmp_path, today=date(2026, 10, 22)) == set()


def test_missing_or_broken_file_is_empty(tmp_path: Path):
    assert load_buysave_upcs(tmp_path, today=date(2026, 10, 22)) == set()
    (tmp_path / "buysave.json").write_text("{", encoding="utf-8")
    assert load_buysave_upcs(tmp_path, today=date(2026, 10, 22)) == set()
