import json

import pytest

from datetime import date

from property_scout.brief import EMIRATES
from property_scout.messages import LANGUAGES, UI, aed, long_date, pct
from property_scout.report import to_data, to_html, to_markdown
from property_scout.scoring import assess


@pytest.fixture
def result(make_brief, make_listing, today):
    brief = make_brief(client="A & B <Family>", areas=["Dubai Marina"])
    listings = [
        make_listing(benchmark_psf=2600, annual_rent_aed=130_000, service_charge_psf=17, verified=True, observed_on=today.isoformat()),
        make_listing(url="https://b.example/dup?x=1&y=2", price_aed=1_820_000),
        make_listing(url="https://c.example/2", building="Tower <B>", completion="offplan", sale_type="primary", handover="2028-Q2", payment_plan={"on_booking": 20, "during_construction": 40, "on_handover": 40}),
        make_listing(url="https://d.example/3", building="Dear Tower", price_aed=9_000_000),
    ]
    return assess(brief, listings, today)


class TestFormatting:
    def test_aed_per_language(self):
        assert aed(1234567.4) == "AED 1,234,567"
        assert aed(1234567.4, "ru") == "1 234 567 AED"

    def test_pct(self):
        assert pct(0.0734) == "7.3%"
        assert pct(0.05, signed=True) == "+5.0%"
        assert pct(-0.076, signed=True) == "\u22127.6%"

    def test_pct_uses_a_decimal_comma_in_russian(self):
        assert pct(0.0734, lang="ru") == "7,3%"
        assert pct(-0.076, signed=True, lang="ru") == "\u22127,6%"

    def test_property_types_are_translated(self, result):
        assert "квартира" in to_markdown(result, "ru")
        assert "apartment" in to_markdown(result, "en")

    def test_languages_define_the_same_labels(self):
        assert set(UI["en"]) == set(UI["ru"])

    @pytest.mark.parametrize("lang", LANGUAGES)
    def test_every_emirate_has_a_name(self, lang):
        assert all(UI[lang][f"emirate.{emirate}"] for emirate in EMIRATES)

    def test_dates_read_naturally(self):
        assert long_date(date(2026, 11, 9)) == "9 November 2026"
        assert long_date(date(2026, 11, 9), "ru") == "09.11.2026"

    def test_report_names_the_emirate_in_the_report_language(self, result):
        assert "Дубай" in to_html(result, "ru") and "Dubai" in to_html(result, "en")


class TestData:
    def test_counts_reconcile(self, result):
        shortlisted = [a for a in result.ranked if a.verdict == "shortlist"]
        assert 0 < len(shortlisted) < len(result.ranked)
        counts = to_data(result)["counts"]
        assert counts == {"received": 4, "unique": 3, "ranked": 2, "shortlisted": len(shortlisted), "rejected": 1}

    def test_is_json_serialisable_and_ranked_in_order(self, result):
        data = json.loads(json.dumps(to_data(result)))
        assert [row["rank"] for row in data["ranked"]] == [1, 2]
        assert data["ranked"][0]["score"] >= data["ranked"][1]["score"]
        assert data["ranked"][0]["duplicate_urls"] == ["https://b.example/dup?x=1&y=2"]
        assert data["rejected"][0]["reasons"]

    def test_top_limits_the_ranked_list_only(self, result):
        data = to_data(result, top=1)
        assert len(data["ranked"]) == 1
        assert data["counts"]["ranked"] == 2

    def test_costs_are_itemised_and_sum_to_the_outlay(self, result):
        row = to_data(result)["ranked"][0]
        assert row["costs"]
        assert row["price_aed"] + sum(c["amount_aed"] for c in row["costs"]) == pytest.approx(row["total_outlay_aed"])


class TestMarkdown:
    @pytest.mark.parametrize("lang", LANGUAGES)
    def test_contains_every_listing_and_the_method(self, result, lang):
        text = to_markdown(result, lang)
        assert text.startswith(f"# {UI[lang]['title']}")
        for assessment in result.ranked:
            assert assessment.listing.url in text
        assert result.rejected[0].listing.url in text
        assert UI[lang]["method"] in text

    def test_empty_ranking_says_so(self, make_brief, today):
        assert UI["en"]["none_ranked"] in to_markdown(assess(make_brief(), [], today))


class TestHtml:
    @pytest.mark.parametrize("lang", LANGUAGES)
    def test_is_a_complete_document_in_the_requested_language(self, result, lang):
        html = to_html(result, lang)
        assert html.startswith("<!doctype html>") and html.endswith("</html>")
        assert f"<html lang='{lang}'>" in html
        assert UI[lang]["title"] in html

    def test_escapes_listing_and_client_text(self, result):
        html = to_html(result)
        assert "Tower &lt;B&gt;" in html and "Tower <B>" not in html
        assert "A &amp; B &lt;Family&gt;" in html
        assert "https://b.example/dup?x=1&amp;y=2" in html

    def test_is_self_contained(self, result):
        html = to_html(result)
        assert "<script" not in html and "<link" not in html and "@import" not in html

    def test_empty_ranking_says_so(self, make_brief, today):
        assert UI["ru"]["none_ranked"] in to_html(assess(make_brief(), [], today), "ru")
