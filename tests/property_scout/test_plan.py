from urllib.parse import parse_qs, urlsplit

from property_scout.brief import EMIRATES, PROPERTY_TYPES
from property_scout.costs import GOLDEN_VISA_MIN_AED
from property_scout.plan import EMIRATE_SLUG, MAX_BED_VARIANTS, NEW_PROJECT_TYPE_ID, PF, REGISTER_COPY, TYPE_SLUG, search_plan


def steps(plan, name):
    return [step for step in plan if step["step"] == name]


def remarks(plan):
    return " ".join(step["check"] for step in steps(plan, "note"))


class TestTables:
    def test_every_emirate_has_a_slug(self):
        assert set(EMIRATE_SLUG) == set(EMIRATES)

    def test_searchable_types_are_known_property_types(self):
        assert set(NEW_PROJECT_TYPE_ID) == set(TYPE_SLUG) <= set(PROPERTY_TYPES)


class TestListingUrls:
    def test_slug_form_with_price_and_completion(self, make_brief):
        brief = make_brief(areas=["Jumeirah Village Circle"], property_types=["apartment"], bedrooms_min=0, bedrooms_max=0, budget_max=600_000, market="ready")
        plan = search_plan(brief)
        assert steps(plan, "listings")[0]["url"] == f"{PF}/buy/dubai/studio-apartments-for-sale-jumeirah-village-circle.html?pt=600000&cs=completed"
        assert steps(plan, "note") == []

    def test_short_area_names_become_the_portals_addresses(self, make_brief):
        brief = make_brief(areas=["JLT", "Marina", "Dubai Marina", "Jumeirah Village Circle (JVC)"], property_types=["apartment"], bedrooms_min=1, bedrooms_max=1)
        plan = search_plan(brief)
        slugs = ["jumeirah-lake-towers", "dubai-marina", "jumeirah-village-circle"]
        assert [s["url"].split("-for-sale-")[1].split(".html")[0] for s in steps(plan, "listings")] == slugs
        assert [s["url"].rsplit("/", 1)[1] for s in steps(plan, "sold_benchmark")] == [f"1-bedroom-apartments-{slug}" for slug in slugs]
        assert "not found" in steps(plan, "listings")[0]["check"]

    def test_one_url_per_bedroom_count(self, make_brief):
        brief = make_brief(areas=["Dubai Marina"], property_types=["apartment"], bedrooms_min=1, bedrooms_max=2)
        found = [s["url"] for s in steps(search_plan(brief), "listings")]
        assert len(found) == 2
        assert "/1-bedroom-apartments-for-sale-dubai-marina.html" in found[0]
        assert "/2-bedroom-apartments-for-sale-dubai-marina.html" in found[1]

    def test_emirate_wide_search_without_areas_or_types(self, make_brief):
        brief = make_brief(emirates=["ras_al_khaimah"], market="offplan", budget_min=500_000, size_min_sqft=900)
        parts = urlsplit(steps(search_plan(brief), "listings")[0]["url"])
        assert parts.path == "/en/buy/ras-al-khaimah/properties-for-sale.html"
        assert parse_qs(parts.query) == {"pf": ["500000"], "pt": ["2500000"], "cs": ["off_plan"], "af": ["900"]}

    def test_never_uses_the_robots_disallowed_search_path(self, make_brief):
        brief = make_brief(emirates=list(EMIRATES), areas=["Al Reem Island"], bedrooms_min=1)
        for step in search_plan(brief):
            assert "/en/search" not in step.get("url", "")

    def test_defaults_to_dubai_when_no_emirate_is_given_and_says_so(self, make_brief):
        plan = search_plan(make_brief(emirates=[]))
        assert "/buy/dubai/" in steps(plan, "listings")[0]["url"]
        assert "Dubai is assumed" in remarks(plan)

    def test_a_golden_visa_search_starts_at_the_threshold(self, make_brief):
        brief = make_brief(purpose="golden_visa", budget_max=3_000_000, market="any")
        plan = search_plan(brief)
        for step in steps(plan, "listings") + steps(plan, "new_projects"):
            assert parse_qs(urlsplit(step["url"]).query)["pf"] == [f"{GOLDEN_VISA_MIN_AED:.0f}"]

    def test_a_higher_floor_from_the_brief_is_kept(self, make_brief):
        brief = make_brief(purpose="golden_visa", budget_min=2_400_000, budget_max=3_000_000)
        assert "pf=2400000" in steps(search_plan(brief), "listings")[0]["url"]


class TestWhatThePlanCannotExpress:
    def test_areas_are_not_guessed_across_several_emirates(self, make_brief):
        plan = search_plan(make_brief(emirates=["dubai", "abu_dhabi"], areas=["Al Reem Island"]))
        paths = [urlsplit(s["url"]).path for s in steps(plan, "listings")]
        assert paths == ["/en/buy/dubai/properties-for-sale.html", "/en/buy/abu-dhabi/properties-for-sale.html"]
        assert "one brief per emirate" in remarks(plan)

    def test_what_no_address_can_filter_is_named(self, make_brief):
        brief = make_brief(market="offplan", size_min_sqft=900, handover_by="2028-Q4", sale_type="primary", must_have=["sea view"])
        said = remarks(search_plan(brief))
        for expected in ("cannot filter by size", "handover date", "2028-Q4", "sale type", "'primary'", "must-haves"):
            assert expected in said, expected
        ready = remarks(search_plan(make_brief(market="ready", size_min_sqft=900, handover_by="2028-Q4")))
        assert "cannot filter by size" not in ready and "handover date" not in ready

    def test_a_type_the_portal_cannot_filter_widens_the_search(self, make_brief):
        plan = search_plan(make_brief(property_types=["apartment", "duplex"]))
        assert "/properties-for-sale" in steps(plan, "listings")[0]["url"]
        assert "duplex" in remarks(plan)

    def test_a_wide_bedroom_range_is_cut_and_reported(self, make_brief):
        plan = search_plan(make_brief(bedrooms_min=1, bedrooms_max=1 + MAX_BED_VARIANTS))
        assert len(steps(plan, "listings")) == MAX_BED_VARIANTS
        assert f"1 to {MAX_BED_VARIANTS} bedrooms" in remarks(plan)

    def test_an_open_ended_range_is_reported_too(self, make_brief):
        plan = search_plan(make_brief(bedrooms_min=3))
        assert len(steps(plan, "listings")) == MAX_BED_VARIANTS and "bedrooms are searched" in remarks(plan)

    def test_a_range_that_fits_needs_no_remark(self, make_brief):
        assert steps(search_plan(make_brief(bedrooms_min=1, bedrooms_max=MAX_BED_VARIANTS)), "note") == []


class TestOtherSteps:
    def test_new_projects_only_when_off_plan_is_in_scope(self, make_brief):
        assert steps(search_plan(make_brief(market="ready")), "new_projects") == []
        brief = make_brief(market="offplan", emirates=["abu_dhabi"], bedrooms_min=2, bedrooms_max=2)
        step = steps(search_plan(brief), "new_projects")[0]
        assert step["url"] == f"{PF}/new-projects/lp/abu-dhabi?bdr[]=2&pt=2500000&cs=off_plan"

    def test_new_projects_narrow_to_community_and_single_type(self, make_brief):
        brief = make_brief(areas=["Al Marjan Island"], emirates=["ras_al_khaimah"], property_types=["villa"], budget_min=1_000_000)
        parts = urlsplit(steps(search_plan(brief), "new_projects")[0]["url"])
        assert parts.path == "/en/new-projects/lp/ras-al-khaimah/al-marjan-island"
        assert parse_qs(parts.query) == {"pf": ["1000000"], "pt": ["2500000"], "t": [str(NEW_PROJECT_TYPE_ID["villa"])], "cs": ["off_plan"]}

    def test_new_projects_get_one_page_per_type_the_index_can_filter(self, make_brief):
        brief = make_brief(market="offplan", property_types=["villa", "townhouse"])
        pages = [parse_qs(urlsplit(s["url"]).query)["t"] for s in steps(search_plan(brief), "new_projects")]
        assert pages == [[str(NEW_PROJECT_TYPE_ID["villa"])], [str(NEW_PROJECT_TYPE_ID["townhouse"])]]

    def test_a_type_the_index_cannot_filter_means_the_unfiltered_page(self, make_brief):
        found = steps(search_plan(make_brief(market="offplan", property_types=["villa", "duplex"])), "new_projects")
        assert len(found) == 1 and "t" not in parse_qs(urlsplit(found[0]["url"]).query)

    def test_off_plan_briefs_in_dubai_get_the_register_copy_for_each_area(self, make_brief):
        plan = search_plan(make_brief(market="offplan", areas=["JVC", "Arjan"]))
        assert [s["url"] for s in steps(plan, "register")] == [f"{REGISTER_COPY}/jumeirah-village-circle", f"{REGISTER_COPY}/arjan"]
        assert "not the register" in steps(plan, "register")[0]["check"]
        assert steps(search_plan(make_brief(market="ready", areas=["JVC"])), "register") == []
        assert steps(search_plan(make_brief(market="offplan", emirates=["abu_dhabi"], areas=["Yas Island"])), "register") == []

    def test_benchmarks_carry_the_bedroom_count_only_for_apartments(self, make_brief):
        villas = search_plan(make_brief(areas=["Dubai Hills"], property_types=["villa"], bedrooms_min=4, bedrooms_max=4))
        mixed = search_plan(make_brief(areas=["Dubai Hills"], bedrooms_min=1, bedrooms_max=2))
        flats = search_plan(make_brief(areas=["Dubai Hills"], property_types=["apartment"], bedrooms_min=0, bedrooms_max=1))
        assert [s["url"] for s in steps(villas, "sold_benchmark")] == [f"{PF}/transactions/sold/dubai/dubai-hills-estate"]
        assert [s["url"] for s in steps(mixed, "rent_benchmark")] == [f"{PF}/transactions/rented/dubai/dubai-hills-estate"]
        assert [s["url"].rsplit("/", 1)[1] for s in steps(flats, "sold_benchmark")] == ["studio-apartments-dubai-hills-estate", "1-bedroom-apartments-dubai-hills-estate"]
        assert "?page=2" in steps(flats, "sold_benchmark")[0]["check"]

    def test_no_step_pages_through_filtered_results(self, make_brief):
        for step in search_plan(make_brief(areas=["Dubai Marina"], bedrooms_min=1)):
            assert "page=" not in step.get("url", "")

    def test_sold_and_rent_benchmarks_per_area(self, make_brief):
        plan = search_plan(make_brief(areas=["Dubai Marina", "Business Bay"]))
        assert [s["url"] for s in steps(plan, "sold_benchmark")] == [
            f"{PF}/transactions/sold/dubai/dubai-marina",
            f"{PF}/transactions/sold/dubai/business-bay",
        ]
        assert "location line" in steps(plan, "sold_benchmark")[0]["check"]
        assert steps(plan, "rent_benchmark")[0]["url"] == f"{PF}/transactions/rented/dubai/dubai-marina"
        assert "renewals" in steps(plan, "rent_benchmark")[0]["check"]

    def test_benchmarks_are_offered_for_dubai_alone(self, make_brief):
        for emirates in (["abu_dhabi"], ["dubai", "abu_dhabi"]):
            plan = search_plan(make_brief(emirates=emirates, areas=["Al Reem Island"]))
            assert steps(plan, "sold_benchmark") == [] and steps(plan, "rent_benchmark") == []

    def test_lead_queries_carry_the_brief(self, make_brief):
        plan = search_plan(make_brief(areas=["Dubai Marina"], bedrooms_min=1, market="offplan"))
        lead = steps(plan, "leads")[0]
        assert "1 bedroom" in lead["query"] and "off-plan" in lead["query"] and "Dubai Marina" in lead["query"]
        villas = steps(search_plan(make_brief(property_types=["villa"], bedrooms_min=4)), "leads")[0]["query"]
        assert "4 bedroom villa" in villas
        assert "lead" in lead["check"]
        assert steps(plan, "launch_news")

    def test_every_step_says_how_to_check_it(self, make_brief):
        plan = search_plan(make_brief(emirates=[], areas=["Dubai Marina"], market="any"))
        assert steps(plan, "note")
        for step in plan:
            assert step["check"]
            assert step["step"] == "note" or "url" in step or "query" in step
