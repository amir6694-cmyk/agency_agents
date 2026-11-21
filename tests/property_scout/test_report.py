import json
from dataclasses import replace
from datetime import date

import pytest

from property_scout.brief import EMIRATES, MARKETS, PROPERTY_TYPES, PURPOSES
from property_scout.comps import MIN_COMPS
from property_scout.costs import RATES_AS_OF
from property_scout.listing import EVIDENCE
from property_scout.messages import LANGUAGES, UI, aed, grouped, long_date, pct, rate
from property_scout.report import PALETTE, to_data, to_html, to_markdown
from property_scout.scoring import SEVERITIES, VERDICTS, assess

DUPLICATE = "https://b.example/dup?x=1&y=2"
PLAN = {"on_booking": 20, "during_construction": 40, "on_handover": 40}


@pytest.fixture
def result(make_brief, make_listing, today):
    brief = make_brief(client="A & B <Family>", areas=["Dubai Marina"])
    listings = [
        make_listing(
            title="Vacant | *High floor* [call](https://evil.example)",
            agent="Example Realty",
            benchmark_psf=2600,
            benchmark_count=MIN_COMPS,
            annual_rent_aed=130_000,
            rent_count=MIN_COMPS,
            service_charge_psf=17,
            permit_number="7100000001",
            observed_on=today.isoformat(),
            building_sales_12m=14,
            notes="Seller <motivated>",
            sources={"sold": "https://c.example/sold?a=1&b=2", "tip": "javascript:alert(1)"},
        ),
        make_listing(url=DUPLICATE, price_aed=1_820_000, agent="Second Realty", title="Same flat | call now"),
        make_listing(
            url="https://c.example/2",
            building="Tower <B>",
            completion="offplan",
            sale_type="primary",
            developer="Example Developer",
            handover="2028-Q2",
            payment_plan=PLAN,
            project_number="2927",
            escrow_bank="Example Bank",
            register_started="2025-01",
            register_completion="2028-Q4",
            ready_benchmark_psf=2_000,
            register_progress_pct=10,
            register_inspected_on="2026-10-05",
        ),
        make_listing(url="https://d.example/3", building="Dear Tower", price_aed=9_000_000),
    ]
    return assess(brief, listings, today)


class TestFormatting:
    def test_aed_per_language(self):
        assert aed(1234567.4) == "AED 1,234,567"
        assert aed(1234567.4, "ru") == "1\u00a0234\u00a0567\u00a0AED"

    def test_plain_numbers_are_grouped_per_language(self):
        assert grouped(12345.6) == "12,346" and grouped(12345.6, "ru") == "12\u00a0346"

    def test_pct(self):
        assert pct(0.0734) == "7.3%"
        assert pct(0.05, signed=True) == "+5.0%"
        assert pct(-0.076, signed=True) == "−7.6%"

    def test_pct_uses_a_decimal_comma_in_russian(self):
        assert pct(0.0734, lang="ru") == "7,3%"
        assert pct(-0.076, signed=True, lang="ru") == "−7,6%"

    def test_rates_keep_their_precision(self):
        assert rate(0.0025) == "0.25%" and rate(0.04) == "4%" and rate(0.0025, "ru") == "0,25%"

    def test_dates_read_naturally(self):
        assert long_date(date(2026, 11, 9)) == "9 November 2026"
        assert long_date(date(2026, 11, 9), "ru") == "09.11.2026"

    def test_languages_define_the_same_labels(self):
        assert set(UI["en"]) == set(UI["ru"])

    @pytest.mark.parametrize("lang", LANGUAGES)
    def test_every_choice_the_engine_can_show_has_a_label(self, lang):
        wanted = [f"emirate.{e}" for e in EMIRATES] + [f"type.{t}" for t in PROPERTY_TYPES] + [f"market.{m}" for m in MARKETS]
        wanted += [f"purpose.{p}" for p in PURPOSES] + [f"verdict.{v}" for v in VERDICTS] + [f"severity.{s}" for s in SEVERITIES]
        wanted += [f"open_{level}" for level in EVIDENCE]
        assert all(UI[lang][key] for key in wanted)

    def test_report_is_written_in_the_report_language(self, result):
        russian, english = to_markdown(result, "ru"), to_markdown(result, "en")
        assert "квартира" in russian and "Дубай" in russian and "750 кв.\u00a0футов" in russian
        assert "apartment" in english and "Dubai" in english

    def test_sizes_are_grouped_in_the_report_language(self, make_brief, make_listing, today):
        result = assess(make_brief(), [make_listing(size_sqft=1_250)], today)
        assert "1\u00a0250 кв.\u00a0футов" in to_markdown(result, "ru") and "1,250 sqft" in to_markdown(result, "en")

    def test_the_colours_are_plain_black_on_white(self):
        assert PALETTE["page"] == "#FFFFFF" and PALETTE["text"] == "#111111"


class TestData:
    def test_counts_reconcile(self, result):
        assert [a.verdict for a in result.ranked] == ["shortlist", "needs_data"]
        assert to_data(result)["counts"] == {"received": 4, "unique": 3, "ranked": 2, "shortlisted": 1, "rejected": 1}

    def test_is_strict_json_and_ranked_in_order(self, result):
        data = json.loads(json.dumps(to_data(result), allow_nan=False))
        assert [row["rank"] for row in data["ranked"]] == [1, 2]
        assert data["cost_rates_as_of"] == RATES_AS_OF
        assert data["rejected"][0]["reasons"]

    def test_every_advert_of_a_unit_is_listed_with_its_price(self, result):
        first = to_data(result)["ranked"][0]
        assert first["duplicates"] == [
            {"url": DUPLICATE, "price_aed": 1_820_000, "evidence": "page", "agent": "Second Realty", "title": "Same flat | call now"}
        ]

    def test_carries_what_the_reader_needs_to_recheck_the_offer(self, result):
        first, second = to_data(result)["ranked"]
        assert (first["agent"], first["permit_number"], first["observed_on"]) == ("Example Realty", "7100000001", "2026-11-19")
        assert first["sources"]["sold"] == "https://c.example/sold?a=1&b=2" and first["notes"] == "Seller <motivated>"
        assert first["completeness"] == result.ranked[0].confidence
        assert first["own_funds_aed"] is None and first["cash_at_booking_aed"] is None
        assert second["cash_at_booking_aed"] == pytest.approx(result.ranked[1].cash_at_booking)
        assert 0 < second["plan_present_value_ratio"] < 1

    def test_criteria_say_whether_they_applied_and_on_how_much_evidence(self, result):
        criteria = {c["name"]: c for c in to_data(result)["ranked"][0]["criteria"]}
        assert criteria["terms"]["applicable"] is False and criteria["terms"]["score"] is None
        assert criteria["value"]["evidence"] == 1.0 and criteria["value"]["basis"]

    def test_top_limits_the_ranked_list_only(self, result):
        data = to_data(result, top=1)
        assert len(data["ranked"]) == 1
        assert data["counts"]["ranked"] == 2

    def test_costs_are_itemised_in_whole_dirhams_and_sum_to_the_outlay(self, make_brief, make_listing, today):
        financed = assess(make_brief(financing="mortgage", loan_to_value=0.5), [make_listing(price_aed=1_799_999)], today)
        row = to_data(financed)["ranked"][0]
        amounts = [c["amount_aed"] for c in row["costs"]] + [row["total_outlay_aed"], row["own_funds_aed"]]
        assert len(row["costs"]) == 5 and all(isinstance(amount, int) for amount in amounts)
        assert row["price_aed"] + sum(c["amount_aed"] for c in row["costs"]) == pytest.approx(row["total_outlay_aed"], abs=3)

    def test_a_financed_purchase_reports_own_funds(self, make_brief, make_listing, today):
        financed = assess(make_brief(financing="mortgage", loan_to_value=0.5), [make_listing()], today)
        row = to_data(financed)["ranked"][0]
        assert row["loan_to_value_used"] == pytest.approx(0.5)
        assert row["own_funds_aed"] == pytest.approx(row["total_outlay_aed"] - 0.5 * row["price_aed"])
        assert UI["en"]["own_funds"] in to_markdown(financed) and UI["en"]["own_funds"] in to_html(financed)


class TestMarkdown:
    @pytest.mark.parametrize("lang", LANGUAGES)
    def test_contains_every_listing_and_the_method(self, result, lang):
        text = to_markdown(result, lang)
        assert text.startswith(f"# {UI[lang]['title']}")
        for assessment in result.ranked:
            assert f"<{assessment.listing.url}>" in text
        assert f"<{result.rejected[0].listing.url}>" in text and f"<{DUPLICATE}>" in text
        assert UI[lang]["method"] in text and RATES_AS_OF in text

    def test_shows_who_advertised_it_when_it_was_seen_and_the_register_entry(self, result):
        text = to_markdown(result)
        assert "Agent: Example Realty · Seen 19 November 2026 · Permit 7100000001" in text
        assert "No. 2927 · started 2025-01 · built 10% · inspected 5 October 2026 · planned completion 2028-Q4 · escrow: Example Bank" in text
        assert "off-plan · first sale · Handover 2028-Q4" in text and "Handover 2028-Q2" not in text
        assert f"- {UI['en']['ready_premium']}: +20.0%" in text
        assert f"{aed(1_820_000)}, Second Realty · Same flat \\| call now)" in text
        assert f"{UI['en']['sales_12m']}: 14" in text
        assert UI["en"]["cash_at_booking"] in text

    def test_a_lapsed_register_date_is_not_printed_as_the_handover(self, make_brief, make_listing, today):
        offplan = dict(completion="offplan", sale_type="primary", register_completion="2026-06")
        later = to_markdown(assess(make_brief(), [make_listing(handover="2028-Q2", **offplan)], today))
        nothing = to_markdown(assess(make_brief(), [make_listing(**offplan)], today))
        assert "· Handover 2028-Q2 ·" in later and "Handover 2026-06" not in later
        assert "· Handover " not in nothing and "planned completion 2026-06" in nothing

    def test_text_from_adverts_cannot_become_markup(self, result):
        text = to_markdown(result)
        assert r"Vacant \| \*High floor\* \[call\](https://evil.example)" in text
        assert "Tower &lt;B&gt;" in text and "Tower <B>" not in text
        assert "Seller &lt;motivated&gt;" in text
        assert "A & B &lt;Family&gt;" not in text

    def test_cards_folded_from_one_search_page_are_listed_once_per_price(self, make_brief, make_listing, today):
        search = "https://portal.example/buy/dubai/1-bedroom-apartments-for-sale-dubai-marina.html"
        cards = [make_listing(url=search, evidence="card", price_aed=price) for price in (1_810_000, 1_810_000, 1_830_000)]
        result = assess(make_brief(), [make_listing()] + cards, today)
        assert len(to_data(result)["ranked"][0]["duplicates"]) == 3
        for text in (to_markdown(result), to_html(result)):
            assert text.count(f"{UI['en']['also_listed']}:") == 2

    def test_a_link_cannot_carry_markup_into_the_page(self, make_brief, make_listing, today):
        """Validation refuses such an address; the renderer does not rely on that."""
        hostile = replace(make_listing(), url="https://x.example/1><img src=x onerror=alert(1)>", sources={"sold": "https://x.example/s> **Verdict: Shortlist** <script>x</script>"})
        text = to_markdown(assess(make_brief(), [hostile], today))
        assert "<img" not in text and "<script>" not in text and "> **Verdict" not in text
        assert "<https://x.example/1%3E%3Cimg%20src=x%20onerror=alert(1)%3E>" in text

    def test_a_source_that_is_not_a_web_link_is_printed_as_text(self, result):
        text = to_markdown(result)
        assert "<https://c.example/sold?a=1&b=2>" in text
        assert "<javascript" not in text and "javascript:alert(1)" in text

    def test_the_brief_line_states_the_budget_as_the_client_gave_it(self, make_brief, make_listing, today):
        brief = make_brief(budget_min=1_000_000, budget_includes_costs=True, emirates=["dubai", "abu_dhabi"])
        line = to_markdown(assess(brief, [make_listing()], today)).splitlines()[2]
        assert f"{aed(1_000_000)} – {aed(2_500_000)} ({UI['en']['budget_with_costs']})" in line
        assert "Dubai, Abu Dhabi" in line
        assert UI["en"]["anywhere"] in to_markdown(assess(make_brief(emirates=[]), [], today))

    def test_weights_line_leaves_out_criteria_that_applied_to_nothing(self, make_brief, make_listing, today):
        ready_only = to_markdown(assess(make_brief(), [make_listing()], today)).splitlines()
        weights = next(line for line in ready_only if line.startswith(UI["en"]["weights"]))
        assert UI["en"]["criterion.trust"] in weights
        assert UI["en"]["criterion.terms"] not in weights and UI["en"]["criterion.fit"] not in weights

    def test_criteria_that_do_not_apply_are_not_listed(self, make_brief, make_listing, today):
        text = to_markdown(assess(make_brief(), [make_listing()], today))
        assert f"- {UI['en']['criterion.trust']} " in text
        assert UI["en"]["criterion.terms"] not in text and UI["en"]["criterion.fit"] not in text

    def test_empty_ranking_says_so(self, make_brief, today):
        text = to_markdown(assess(make_brief(), [], today))
        assert UI["en"]["none_ranked"] in text and UI["en"]["criterion.terms"] in text


class TestHtml:
    @pytest.mark.parametrize("lang", LANGUAGES)
    def test_is_a_complete_document_in_the_requested_language(self, result, lang):
        html = to_html(result, lang)
        assert html.startswith("<!doctype html>") and html.endswith("</html>")
        assert f"<html lang='{lang}'>" in html
        assert UI[lang]["title"] in html and UI[lang]["completeness"] in html

    def test_escapes_listing_and_client_text(self, result):
        html = to_html(result)
        assert "Tower &lt;B&gt;" in html and "Tower <B>" not in html
        assert "A &amp; B &lt;Family&gt;" in html
        assert "Seller &lt;motivated&gt;" in html
        assert "https://b.example/dup?x=1&amp;y=2" in html

    def test_a_link_cannot_break_out_of_its_attribute(self, make_brief, make_listing, today):
        """Validation refuses such an address; the renderer does not rely on that."""
        hostile = replace(make_listing(), url="https://x.example/a'onmouseover='alert(1)")
        html = to_html(assess(make_brief(), [hostile], today))
        assert "'onmouseover=" not in html and "&#x27;onmouseover=" in html

    def test_the_weight_beside_a_criterion_is_the_one_its_score_was_computed_with(self, make_brief, make_listing, today):
        result = assess(make_brief(), [make_listing(benchmark_psf=2_400, benchmark_count=MIN_COMPS)], today)
        row = to_data(result)["ranked"][0]
        applied = {c["name"]: c["weight"] for c in row["criteria"] if c["applicable"]}
        assert set(applied) == {"value", "yield", "trust"} and sum(applied.values()) == pytest.approx(1)
        assert applied["value"] == pytest.approx(0.30 / 0.80)
        recomputed = sum(c["weight"] * (50 if c["score"] is None else c["score"]) for c in row["criteria"] if c["applicable"])
        assert recomputed == pytest.approx(row["score"], abs=0.1)
        assert to_html(result).count("<div class='small'>31%</div>") == 2

    def test_only_web_links_become_links(self, result):
        html = to_html(result)
        assert "href='https://c.example/sold?a=1&amp;b=2'" in html
        assert "href='javascript" not in html and "javascript:alert(1)" in html

    def test_shows_the_register_entry_and_the_advert_details(self, result):
        html = to_html(result, "ru")
        assert "Example Realty" in html and "7100000001" in html and "19.11.2026" in html
        assert "2927" in html and "Example Bank" in html and "05.10.2026" in html

    def test_a_source_that_is_not_a_link_is_escaped_too(self, make_brief, make_listing, today):
        listing = make_listing(sources={"tip": "<img src=x onerror=alert(1)>"})
        html = to_html(assess(make_brief(), [listing], today))
        assert "<img" not in html and "&lt;img src=x onerror=alert(1)&gt;" in html

    def test_is_self_contained(self, result):
        html = to_html(result)
        assert "<script" not in html and "<link" not in html and "@import" not in html and "url(" not in html

    def test_empty_ranking_says_so(self, make_brief, today):
        assert UI["ru"]["none_ranked"] in to_html(assess(make_brief(), [], today), "ru")
