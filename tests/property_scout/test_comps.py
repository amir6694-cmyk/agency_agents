from statistics import median

import pytest

from property_scout.comps import MIN_COMPS, SIZE_BAND, CompsError, summarise


def row(price, size, day=None, completion=None):
    data = {"price_aed": price, "size_sqft": size}
    if day:
        data["date"] = day
    if completion:
        data["completion"] = completion
    return data


class TestSummarise:
    def test_median_beats_a_distorting_outlier(self, today):
        rows = [row(1_500_000, 750), row(1_560_000, 760), row(1_520_000, 745), row(1_540_000, 755), row(6_000_000, 760)]
        summary = summarise(rows, today)
        assert summary.median_psf == pytest.approx(median(r["price_aed"] / r["size_sqft"] for r in rows))
        assert summary.median_psf < 2100
        assert summary.high_psf > 7000

    def test_drops_rows_outside_the_size_band(self, today):
        rows = [row(1_500_000, 750), row(3_000_000, 750 * (1 + 2 * SIZE_BAND))]
        summary = summarise(rows, today, subject_size_sqft=750)
        assert summary.used == 1
        assert summary.dropped["size"] == 1

    def test_size_band_edges(self, today):
        inside = row(1_500_000, 750 * (1 + SIZE_BAND))
        near = row(1_500_000, 750 * (1 - SIZE_BAND * 0.75))
        outside = row(1_500_000, 750 * (1 + SIZE_BAND) + 1)
        summary = summarise([inside, near, outside], today, subject_size_sqft=750)
        assert summary.used == 2 and summary.dropped["size"] == 1

    def test_negative_figures_are_incomplete_rows(self, today):
        summary = summarise([row(-1_500_000, 750), row(1_500_000, -750)], today)
        assert summary.used == 0 and summary.dropped["incomplete"] == 2

    def test_drops_rows_older_than_the_window(self, today):
        rows = [row(1_500_000, 750, "2026-10-30"), row(1_900_000, 750, "2026-07-01")]
        summary = summarise(rows, today)
        assert summary.used == 1
        assert summary.dropped["date"] == 1
        assert summarise(rows, today, months=6).used == 2

    def test_window_is_counted_to_the_day(self, today):
        inside = row(1_500_000, 750, "2026-08-19")
        outside = row(1_900_000, 750, "2026-08-18")
        summary = summarise([inside, outside], today, months=3)
        assert summary.used == 1 and summary.dropped["date"] == 1

    def test_window_handles_short_months_and_year_ends(self):
        from datetime import date

        rows = [row(1, 1, "2025-11-30"), row(1, 1, "2025-11-29")]
        assert summarise(rows, date(2026, 2, 28), months=3).used == 2
        assert summarise(rows, date(2026, 3, 31), months=4).used == 1

    def test_window_can_be_widened(self, today):
        rows = [row(1_500_000, 750, "2026-10-30"), row(1_900_000, 750, "2025-08-01")]
        summary = summarise(rows, today, months=6)
        assert summary.used == 1
        assert summary.dropped["date"] == 1

    def test_keeps_off_plan_and_ready_apart(self, today):
        rows = [row(1_500_000, 750, completion="Ready"), row(1_900_000, 750, completion="Off-plan")]
        summary = summarise(rows, today, completion="ready")
        assert summary.used == 1
        assert summary.dropped["completion"] == 1
        assert summary.median_psf == pytest.approx(2000)

    def test_counts_incomplete_rows(self, today):
        summary = summarise([row(1_500_000, 750), {"price_aed": 1_000_000}, row(0, 700)], today)
        assert summary.dropped["incomplete"] == 2

    def test_few_comps_are_flagged_thin(self, today):
        assert summarise([row(1_500_000, 750)] * (MIN_COMPS - 1), today).thin
        assert not summarise([row(1_500_000, 750)] * MIN_COMPS, today).thin

    def test_nothing_usable_gives_no_figures(self, today):
        summary = summarise([], today)
        assert summary.used == 0 and summary.median_psf is None and summary.thin

    def test_rejects_rows_that_are_not_objects(self, today):
        with pytest.raises(CompsError):
            summarise([[1_500_000, 750]], today)
