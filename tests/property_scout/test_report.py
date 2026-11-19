import json

import pytest

from property_scout.messages import LANGUAGES, UI, aed, pct
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
        assert pct(-0.076, signed=True) == "-7.6%"

    def test_languages_define_the_same_labels(self):
        assert set(UI["en"]) == set(UI["ru"])


class TestData:
    def test_counts_reconcile(self, result):
        counts = to_data(result)["counts"]
        assert counts == {"received": 4, "unique": 3, "ranked": 2, "shortlisted": counts["shortlisted"], "rejected": 1}

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

    def test_has_no_scripts(self, result):
        assert "<script" not in to_html(result)

    def test_empty_ranking_says_so(self, make_brief, today):
        assert UI["ru"]["none_ranked"] in to_html(assess(make_brief(), [], today), "ru")
