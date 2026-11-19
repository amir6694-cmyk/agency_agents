from urllib.parse import parse_qs, urlsplit

import pytest

from property_scout.brief import EMIRATES
from property_scout.plan import EMIRATE_SLUG, NEW_PROJECT_TYPE_ID, PF, TYPE_SLUG, search_plan


def steps(plan, name):
    return [step for step in plan if step["step"] == name]


class TestTables:
    def test_every_emirate_has_a_slug(self):
        assert set(EMIRATE_SLUG) == set(EMIRATES)

    def test_new_project_types_are_ones_the_listing_search_knows(self):
        assert set(NEW_PROJECT_TYPE_ID) == set(TYPE_SLUG)


class TestListingUrls:
    def test_slug_form_with_price_and_completion(self, make_brief):
        brief = make_brief(areas=["Jumeirah Village Circle"], property_types=["apartment"], bedrooms_min=0, bedrooms_max=0, budget_max=600_000, market="ready")
        url = steps(search_plan(brief), "listings")[0]["url"]
        assert url == f"{PF}/buy/dubai/studio-apartments-for-sale-jumeirah-village-circle.html?pt=600000&cs=completed"

    def test_one_url_per_bedroom_count(self, make_brief):
        brief = make_brief(areas=["Dubai Marina"], property_types=["apartment"], bedrooms_min=1, bedrooms_max=2)
        urls = [s["url"] for s in steps(search_plan(brief), "listings")]
        assert len(urls) == 2
        assert "/1-bedroom-apartments-for-sale-dubai-marina.html" in urls[0]
        assert "/2-bedroom-apartments-for-sale-dubai-marina.html" in urls[1]

    def test_emirate_wide_search_without_areas_or_types(self, make_brief):
        brief = make_brief(emirates=["ras_al_khaimah"], market="offplan", budget_min=500_000, size_min_sqft=900)
        url = steps(search_plan(brief), "listings")[0]["url"]
        parts = urlsplit(url)
        assert parts.path == "/en/buy/ras-al-khaimah/properties-for-sale.html"
        assert parse_qs(parts.query) == {"pf": ["500000"], "pt": ["2500000"], "cs": ["off_plan"], "af": ["900"]}

    def test_never_uses_the_robots_disallowed_search_path(self, make_brief):
        brief = make_brief(emirates=list(EMIRATES), areas=["Al Reem Island"], bedrooms_min=1)
        for step in search_plan(brief):
            assert "/en/search" not in step.get("url", "")

    def test_defaults_to_dubai_when_no_emirate_is_given(self, make_brief):
        assert "/buy/dubai/" in steps(search_plan(make_brief(emirates=[])), "listings")[0]["url"]


class TestOtherSteps:
    def test_new_projects_only_when_off_plan_is_in_scope(self, make_brief):
        assert steps(search_plan(make_brief(market="ready")), "new_projects") == []
        brief = make_brief(market="offplan", emirates=["abu_dhabi"], bedrooms_min=2, bedrooms_max=2)
        step = steps(search_plan(brief), "new_projects")[0]
        assert step["url"] == f"{PF}/new-projects/lp/abu-dhabi?bdr[]=2&pt=2500000&cs=off_plan"

    def test_new_projects_narrow_to_community_and_single_type(self, make_brief):
        brief = make_brief(areas=["Al Marjan Island"], emirates=["ras_al_khaimah"], property_types=["villa"], budget_min=1_000_000)
        step = steps(search_plan(brief), "new_projects")[0]
        parts = urlsplit(step["url"])
        assert parts.path == "/en/new-projects/lp/ras-al-khaimah/al-marjan-island"
        assert parse_qs(parts.query) == {"pf": ["1000000"], "pt": ["2500000"], "t": [str(NEW_PROJECT_TYPE_ID["villa"])], "cs": ["off_plan"]}

    def test_no_step_pages_through_filtered_results(self, make_brief):
        for step in search_plan(make_brief(areas=["Dubai Marina"], bedrooms_min=1)):
            assert "page=" not in step.get("url", "")

    def test_sold_benchmark_per_area(self, make_brief):
        plan = search_plan(make_brief(areas=["Dubai Marina", "Business Bay"]))
        assert [s["url"] for s in steps(plan, "sold_benchmark")] == [
            f"{PF}/transactions/sold/dubai/dubai-marina",
            f"{PF}/transactions/sold/dubai/business-bay",
        ]

    def test_sold_and_rent_benchmarks_are_dubai_only(self, make_brief):
        plan = search_plan(make_brief(emirates=["abu_dhabi"], areas=["Al Reem Island"]))
        assert steps(plan, "sold_benchmark") == [] and steps(plan, "rent_benchmark") == []

    def test_rent_benchmark_matches_the_sold_slug(self, make_brief):
        plan = search_plan(make_brief(areas=["Dubai Marina"]))
        assert steps(plan, "rent_benchmark")[0]["url"] == f"{PF}/transactions/rented/dubai/dubai-marina"

    def test_lead_queries_carry_the_brief(self, make_brief):
        plan = search_plan(make_brief(areas=["Dubai Marina"], bedrooms_min=1, market="offplan"))
        lead = steps(plan, "leads")[0]
        assert "1 bedroom" in lead["query"] and "off-plan" in lead["query"] and "Dubai Marina" in lead["query"]
        assert steps(plan, "launch_news")

    def test_every_step_says_how_to_check_it(self, make_brief):
        for step in search_plan(make_brief(areas=["Dubai Marina"], market="any")):
            assert step["check"] and ("url" in step or "query" in step)
