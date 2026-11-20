import pytest

from property_scout.dedupe import PRICE_TOLERANCE, SHARED_FACTS, SIZE_TOLERANCE, TRACKING_PARAMETERS, canonical_url, dedupe
from property_scout.listing import Listing


def urls(groups):
    return [listing.url for listing, _ in groups]


def folded(groups):
    return {listing.url: [d.url for d in duplicates] for listing, duplicates in groups if duplicates}


class TestCanonicalUrl:
    def test_ignores_scheme_www_trailing_slash_and_page_anchors(self):
        assert canonical_url("https://www.Portal.example/listing/1/#top") == canonical_url("http://portal.example/listing/1")

    @pytest.mark.parametrize("parameter", TRACKING_PARAMETERS + ("utm_source", "utm_campaign"))
    def test_ignores_tracking_parameters(self, parameter):
        assert canonical_url(f"https://portal.example/listing/1?{parameter}=x") == canonical_url("https://portal.example/listing/1")

    def test_keeps_the_parameters_that_name_the_page(self):
        assert canonical_url("https://portal.example/listing?id=1") != canonical_url("https://portal.example/listing?id=2")
        assert canonical_url("https://portal.example/listing?b=2&a=1") == canonical_url("https://portal.example/listing?a=1&b=2&cb=9")

    def test_keeps_routes_carried_in_the_fragment(self):
        assert canonical_url("https://app.example/#/unit/1") != canonical_url("https://app.example/#/unit/2")


class TestSameUnit:
    def test_two_pages_with_one_address_are_one_unit(self, make_listing):
        groups = dedupe([make_listing(), make_listing(url="https://www.portal.example/listing/1?ref=agent")])
        assert len(groups) == 1
        assert folded(groups) == {"https://portal.example/listing/1": ["https://www.portal.example/listing/1?ref=agent"]}

    def test_cards_sharing_a_search_page_are_not_merged_on_the_link(self, make_listing):
        search = "https://portal.example/buy/dubai/1-bedroom-apartments-for-sale-dubai-marina.html?pt=2000000"
        first = make_listing(url=search, evidence="card", building="Tower A", price_aed=1_500_000)
        second = make_listing(url=search, evidence="card", building="Tower B", price_aed=1_550_000)
        assert len(dedupe([first, second])) == 2

    def test_a_card_and_a_page_of_the_same_flat_are_one_unit(self, make_listing):
        card = make_listing(url="https://a.example/search", evidence="card", price_aed=1_790_000)
        page = make_listing(url="https://a.example/listing/7", evidence="page")
        groups = dedupe([card, page])
        assert urls(groups) == ["https://a.example/listing/7"]
        assert folded(groups) == {"https://a.example/listing/7": ["https://a.example/search"]}

    def test_same_unit_from_two_agents_is_represented_by_the_cheaper(self, make_listing):
        dear = make_listing(url="https://a.example/1", price_aed=1_850_000)
        cheap = make_listing(url="https://b.example/2", price_aed=1_800_000, size_sqft=752)
        groups = dedupe([dear, cheap])
        assert folded(groups) == {"https://b.example/2": ["https://a.example/1"]}

    def test_verified_breaks_a_price_tie(self, make_listing):
        plain = make_listing(url="https://a.example/1")
        verified = make_listing(url="https://b.example/2", verified=True)
        assert urls(dedupe([plain, verified])) == ["https://b.example/2"]

    def test_building_names_compare_without_punctuation_or_case(self, make_listing):
        other = make_listing(url="https://a.example/2", building="MARINA GATE-1")
        assert len(dedupe([make_listing(), other])) == 1

    def test_an_equal_permit_number_joins_adverts_that_share_nothing_else(self, make_listing):
        first = make_listing(url="https://a.example/1", building=None, property_type="villa", permit_number="7100000001")
        second = make_listing(url="https://b.example/2", building=None, property_type="villa", permit_number="7100000001")
        assert len(dedupe([first, second])) == 1


class TestDifferentUnits:
    def one_of_each(self, make_listing, **change):
        return dedupe([make_listing(), make_listing(url="https://a.example/2", **change)])

    def test_different_size(self, make_listing):
        assert len(self.one_of_each(make_listing, size_sqft=750 * (1 + 2 * SIZE_TOLERANCE))) == 2
        assert len(self.one_of_each(make_listing, size_sqft=750 * (1 + SIZE_TOLERANCE / 2))) == 1

    def test_different_price(self, make_listing):
        assert len(self.one_of_each(make_listing, price_aed=1_800_000 * (1 + 2 * PRICE_TOLERANCE))) == 2
        assert len(self.one_of_each(make_listing, price_aed=1_800_000 * (1 + PRICE_TOLERANCE / 2))) == 1

    @pytest.mark.parametrize("change", [{"bedrooms": 2}, {"building": "Marina Gate 2"}, {"community": "Business Bay"}, {"completion": "offplan"}])
    def test_a_different_fact_is_a_different_unit(self, make_listing, change):
        assert len(self.one_of_each(make_listing, **change)) == 2

    def test_different_bathrooms(self, make_listing):
        assert len(dedupe([make_listing(bathrooms=1), make_listing(url="https://a.example/2", bathrooms=2)])) == 2

    def test_tenanted_and_vacant_are_different_units(self, make_listing):
        assert len(dedupe([make_listing(tags=["tenanted"]), make_listing(url="https://a.example/2", tags=["vacant"])])) == 2

    @pytest.mark.parametrize("missing", ["bedrooms", "building", "size_sqft"])
    def test_a_missing_fact_never_merges(self, make_listing, missing):
        listings = [make_listing(**{missing: None}), make_listing(url="https://a.example/2", **{missing: None})]
        assert len(dedupe(listings)) == 2

    @pytest.mark.parametrize("kind", ["villa", "townhouse"])
    def test_houses_are_not_merged_on_their_description(self, make_listing, kind):
        listings = [make_listing(property_type=kind), make_listing(url="https://a.example/2", property_type=kind)]
        assert len(dedupe(listings)) == 2

    def test_an_equal_permit_does_not_override_a_contradiction(self, make_listing):
        first = make_listing(permit_number="7100000001")
        second = make_listing(url="https://a.example/2", permit_number="7100000001", bedrooms=3)
        assert len(dedupe([first, second])) == 2

    def test_a_chain_of_near_matches_does_not_grow_past_the_tolerance(self, make_listing):
        first = make_listing(url="https://a.example/1", price_aed=1_800_000)
        bridge = make_listing(url="https://a.example/2", price_aed=1_860_000)
        last = make_listing(url="https://a.example/3", price_aed=1_930_000)
        groups = dedupe([first, last, bridge])
        assert urls(groups) == ["https://a.example/1", "https://a.example/3"]
        assert folded(groups) == {"https://a.example/1": ["https://a.example/2"]}


class TestMerging:
    def test_the_unit_keeps_what_any_advert_showed_about_it(self, make_listing):
        anchor = make_listing(url="https://a.example/1")
        other = make_listing(url="https://b.example/2", price_aed=1_820_000, benchmark_psf=2400, benchmark_count=8, annual_rent_aed=120_000, tags=["balcony"])
        (merged, duplicates), = dedupe([anchor, other])
        assert merged.url == "https://a.example/1" and merged.price_aed == 1_800_000
        assert (merged.benchmark_psf, merged.benchmark_count, merged.annual_rent_aed) == (2400, 8, 120_000)
        assert merged.tags == ["balcony"]
        assert [d.url for d in duplicates] == ["https://b.example/2"]

    def test_the_representative_advert_is_never_overwritten(self, make_listing):
        anchor = make_listing(url="https://a.example/1", benchmark_psf=2300, permit_number="71")
        other = make_listing(url="https://b.example/2", price_aed=1_820_000, benchmark_psf=2600, permit_number="72", agent="Other Realty")
        (merged, _), = dedupe([anchor, other])
        assert merged.benchmark_psf == 2300 and merged.permit_number == "71" and merged.agent == ""

    def test_facts_of_one_advert_are_not_shared(self):
        own = {"url", "price_aed", "evidence", "agent", "permit_number", "verified", "observed_on", "listed_days_ago", "title"}
        assert not own & set(SHARED_FACTS)
        assert set(SHARED_FACTS) <= set(Listing.__dataclass_fields__)

    def test_input_order_does_not_change_the_outcome(self, make_listing):
        listings = [
            make_listing(url="https://a.example/1", price_aed=1_850_000),
            make_listing(url="https://a.example/2", evidence="card"),
            make_listing(url="https://a.example/3", building="Other Tower"),
        ]
        assert urls(dedupe(listings)) == urls(dedupe(listings[::-1]))
