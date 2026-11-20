from datetime import date
from statistics import median

import pytest

from property_scout.comps import CONCENTRATION_LIMIT, MIN_COMPS, SIZE_BAND, CompsError, summarise


def row(price, size, day=None, **extra):
    data = {"price_aed": price, "size_sqft": size, **extra}
    if day:
        data["date"] = day
    return data


class TestSummarise:
    def test_median_beats_a_distorting_outlier(self, today):
        rows = [row(1_500_000, 750), row(1_560_000, 760), row(1_520_000, 745), row(1_540_000, 755), row(6_000_000, 760)]
        summary = summarise(rows, today)
        assert summary.median_psf == pytest.approx(median(r["price_aed"] / r["size_sqft"] for r in rows))
        assert summary.median_price == 1_540_000
        assert summary.low_psf == pytest.approx(2000) and summary.high_psf > 7000

    def test_drops_rows_outside_the_size_band(self, today):
        rows = [row(1_500_000, 750), row(3_000_000, 750 * (1 + 2 * SIZE_BAND))]
        summary = summarise(rows, today, subject_size_sqft=750)
        assert summary.used == 1 and summary.dropped["size"] == 1

    def test_size_band_edges(self, today):
        inside = row(1_500_000, 750 * (1 + SIZE_BAND))
        near = row(1_500_000, 750 * (1 - SIZE_BAND * 0.75))
        outside = row(1_500_000, 750 * (1 + SIZE_BAND) + 1)
        summary = summarise([inside, near, outside], today, subject_size_sqft=750)
        assert summary.used == 2 and summary.dropped["size"] == 1

    def test_drops_rows_older_than_the_window(self, today):
        rows = [row(1_500_000, 750, "2026-10-30"), row(1_900_000, 750, "2026-07-01")]
        summary = summarise(rows, today)
        assert summary.used == 1 and summary.dropped["date"] == 1
        assert summarise(rows, today, months=6).used == 2

    def test_window_is_counted_to_the_day(self, today):
        inside = row(1_500_000, 750, "2026-08-19")
        outside = row(1_900_000, 750, "2026-08-18")
        summary = summarise([inside, outside], today, months=3)
        assert summary.used == 1 and summary.dropped["date"] == 1

    def test_window_handles_short_months_and_year_ends(self):
        rows = [row(1, 1, "2025-11-30"), row(1, 1, "2025-11-29")]
        assert summarise(rows, date(2026, 2, 28), months=3).used == 2
        assert summarise(rows, date(2026, 3, 31), months=4).used == 1

    def test_undated_rows_are_kept_and_the_span_covers_the_dated_ones(self, today):
        rows = [row(1_500_000, 750), row(1_500_000, 750, "2026-10-30"), row(1_500_000, 750, "2026-09-02T00:00:00")]
        summary = summarise(rows, today)
        assert summary.used == 3
        assert (summary.first_date, summary.last_date) == ("2026-09-02", "2026-10-30")

    def test_keeps_off_plan_and_ready_apart(self, today):
        rows = [row(1_500_000, 750, completion="Ready"), row(1_900_000, 750, completion="Off-plan"), row(1_500_000, 750)]
        summary = summarise(rows, today, completion="ready")
        assert summary.used == 2 and summary.dropped["completion"] == 1
        assert summary.median_psf == pytest.approx(2000)

    def test_counts_incomplete_rows(self, today):
        summary = summarise([row(1_500_000, 750), {"price_aed": 1_000_000}, row(0, 700), row(1_000_000, None)], today)
        assert summary.used == 1 and summary.dropped["incomplete"] == 3

    def test_few_comps_are_flagged_thin(self, today):
        assert summarise([row(1_500_000, 750)] * (MIN_COMPS - 1), today).thin
        assert not summarise([row(1_500_000, 750)] * MIN_COMPS, today).thin

    def test_nothing_usable_gives_no_figures(self, today):
        summary = summarise([], today)
        assert summary.used == 0 and summary.median_psf is None and summary.thin and not summary.concentrated


class TestNewLeases:
    rows = [
        row(120_000, 750, contract="New", term_months=12),
        row(118_000, 750, contract="new"),
        row(95_000, 750, contract="Renewal", term_months=12),
        row(60_000, 750, contract="new", term_months=6),
        row(122_000, 750),
    ]

    def test_renewals_and_short_lets_are_dropped_when_asked(self, today):
        summary = summarise(self.rows, today, new_leases=True)
        assert summary.used == 3 and summary.dropped["contract"] == 2
        assert summary.median_price == 120_000

    def test_every_contract_counts_otherwise(self, today):
        assert summarise(self.rows, today).used == len(self.rows)


class TestConcentration:
    def test_one_project_supplying_most_rows_is_reported(self, today):
        rows = [row(1_500_000, 750, project="Tower A")] * 3 + [row(1_500_000, 750, project="tower-a")] + [row(1_500_000, 750, project="Tower B")] * 2
        summary = summarise(rows, today)
        assert summary.largest_project_share == pytest.approx(4 / 6)
        assert summary.concentrated

    def test_an_even_spread_is_not(self, today):
        rows = [row(1_500_000, 750, project=name) for name in ("A", "B", "C", "D")]
        summary = summarise(rows, today)
        assert summary.largest_project_share == pytest.approx(0.25) and not summary.concentrated

    def test_exactly_at_the_limit_is_not_concentrated(self, today):
        rows = [row(1_500_000, 750, project="A")] * 2 + [row(1_500_000, 750, project="B"), row(1_500_000, 750, project="C")]
        assert summarise(rows, today).largest_project_share == CONCENTRATION_LIMIT
        assert not summarise(rows, today).concentrated

    def test_the_share_is_of_all_rows_used_not_of_the_named_ones(self, today):
        rows = [row(1_500_000, 750, project="A")] * 2 + [row(1_500_000, 750)] * 4
        summary = summarise(rows, today)
        assert summary.largest_project_share == pytest.approx(2 / 6) and not summary.concentrated

    def test_unknown_when_rows_do_not_name_their_project(self, today):
        assert summarise([row(1_500_000, 750)] * 6, today).largest_project_share is None


class TestBadRows:
    def test_rejects_rows_that_are_not_objects(self, today):
        with pytest.raises(CompsError, match="row 1"):
            summarise([[1_500_000, 750]], today)

    @pytest.mark.parametrize(
        "bad",
        [
            {"price_aed": "1,500,000", "size_sqft": 750},
            {"price_aed": -1_500_000, "size_sqft": 750},
            {"price_aed": 1_500_000, "size_sqft": -750},
            {"price_aed": 1_500_000, "size_sqft": 750, "date": "30/10/2026"},
            {"price_aed": 1_500_000, "size_sqft": 750, "completion": 5},
        ],
    )
    def test_a_wrong_value_is_named_with_its_row(self, today, bad):
        with pytest.raises(CompsError, match="row 2"):
            summarise([row(1_500_000, 750), bad], today, completion="ready")
