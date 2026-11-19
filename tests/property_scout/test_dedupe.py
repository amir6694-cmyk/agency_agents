from property_scout.dedupe import PRICE_TOLERANCE, SIZE_TOLERANCE, canonical_url, dedupe


class TestCanonicalUrl:
    def test_ignores_scheme_www_query_and_trailing_slash(self):
        assert canonical_url("https://www.Portal.example/listing/1/?utm=x#top") == canonical_url(
            "http://portal.example/listing/1"
        )


class TestDedupe:
    def test_same_url_is_one_unit(self, make_listing):
        kept, folded = dedupe([make_listing(), make_listing(url="https://www.portal.example/listing/1?ref=agent")])
        assert len(kept) == 1
        assert list(folded.values())[0] == ["https://www.portal.example/listing/1?ref=agent"]

    def test_cards_sharing_a_search_page_are_not_merged_on_the_link(self, make_listing):
        search = "https://portal.example/buy/dubai/1-bedroom-apartments-for-sale-dubai-marina.html?pt=2000000"
        first = make_listing(url=search, evidence="card", building="Tower A", price_aed=1_500_000)
        second = make_listing(url=search, evidence="card", building="Tower B", price_aed=1_900_000)
        kept, folded = dedupe([first, second])
        assert len(kept) == 2 and folded == {}

    def test_stronger_evidence_breaks_a_price_tie(self, make_listing):
        card = make_listing(url="https://a.example/search", evidence="card")
        page = make_listing(url="https://a.example/listing/7", evidence="page")
        kept, _ = dedupe([card, page])
        assert kept[0].url == "https://a.example/listing/7"

    def test_same_unit_from_two_agents_keeps_the_cheaper(self, make_listing):
        dear = make_listing(url="https://a.example/1", price_aed=1_850_000)
        cheap = make_listing(url="https://b.example/2", price_aed=1_800_000, size_sqft=752)
        kept, folded = dedupe([dear, cheap])
        assert [l.url for l in kept] == ["https://b.example/2"]
        assert folded == {"https://b.example/2": ["https://a.example/1"]}

    def test_verified_breaks_a_price_tie(self, make_listing):
        plain = make_listing(url="https://a.example/1")
        verified = make_listing(url="https://b.example/2", verified=True)
        kept, _ = dedupe([plain, verified])
        assert kept[0].url == "https://b.example/2"

    def test_different_size_is_a_different_unit(self, make_listing):
        other = make_listing(url="https://a.example/2", size_sqft=750 * (1 + 2 * SIZE_TOLERANCE))
        kept, folded = dedupe([make_listing(), other])
        assert len(kept) == 2 and folded == {}

    def test_different_price_is_a_different_unit(self, make_listing):
        other = make_listing(url="https://a.example/2", price_aed=1_800_000 * (1 + 2 * PRICE_TOLERANCE))
        assert len(dedupe([make_listing(), other])[0]) == 2

    def test_different_bedrooms_or_building_are_different_units(self, make_listing):
        listings = [
            make_listing(),
            make_listing(url="https://a.example/2", bedrooms=2),
            make_listing(url="https://a.example/3", building="Marina Gate 2"),
        ]
        assert len(dedupe(listings)[0]) == 3

    def test_missing_building_or_size_never_merges(self, make_listing):
        listings = [make_listing(building=None), make_listing(url="https://a.example/2", building=None)]
        assert len(dedupe(listings)[0]) == 2

    def test_off_plan_and_ready_never_merge(self, make_listing):
        listings = [make_listing(), make_listing(url="https://a.example/2", completion="offplan")]
        assert len(dedupe(listings)[0]) == 2

    def test_chains_of_matches_collapse_together(self, make_listing):
        first = make_listing(url="https://a.example/1", price_aed=1_800_000)
        bridge = make_listing(url="https://a.example/2", price_aed=1_860_000)
        last = make_listing(url="https://a.example/3", price_aed=1_930_000)
        kept, folded = dedupe([first, last, bridge])
        assert [l.url for l in kept] == ["https://a.example/1"]
        assert sorted(folded["https://a.example/1"]) == ["https://a.example/2", "https://a.example/3"]

    def test_building_names_compare_without_punctuation_or_case(self, make_listing):
        other = make_listing(url="https://a.example/2", building="MARINA GATE-1")
        assert len(dedupe([make_listing(), other])[0]) == 1
