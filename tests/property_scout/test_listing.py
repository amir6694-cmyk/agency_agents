import pytest

from property_scout.listing import EVIDENCE, PLAN_STAGES, Listing, ListingError


class TestListingParsing:
    def test_price_per_sqft(self, make_listing):
        listing = make_listing(price_aed=1_500_000, size_sqft=750)
        assert listing.price_psf == 2000

    def test_price_per_sqft_needs_size(self, make_listing):
        assert make_listing(size_sqft=None).price_psf is None

    def test_normalises_choices_and_tags(self, make_listing):
        listing = make_listing(completion="Off-Plan", emirate="Ras Al Khaimah", tags=["Sea View"])
        assert listing.completion == "offplan"
        assert listing.emirate == "ras_al_khaimah"
        assert listing.tags == ["sea_view"]

    @pytest.mark.parametrize("level", EVIDENCE)
    def test_accepts_every_evidence_level(self, make_listing, level):
        assert make_listing(evidence=level.upper()).evidence == level

    def test_label_prefers_building_then_community(self, make_listing):
        assert make_listing().label == "Marina Gate 1, Dubai Marina"

    def test_label_falls_back_to_title_then_url(self):
        titled = Listing.from_dict({"url": "https://x.example/1", "price_aed": 1, "evidence": "card", "title": "Sea view flat"})
        bare = Listing.from_dict({"url": "https://x.example/1", "price_aed": 1, "evidence": "card"})
        assert titled.label == "Sea view flat"
        assert bare.label == "https://x.example/1"


class TestListingValidation:
    @pytest.mark.parametrize("missing", ["url", "price_aed", "evidence"])
    def test_requires_url_price_and_evidence_level(self, missing):
        data = {"url": "https://x.example/1", "price_aed": 1_000_000, "evidence": "page"}
        del data[missing]
        with pytest.raises(ListingError, match=missing):
            Listing.from_dict(data)

    @pytest.mark.parametrize("url", ["javascript:alert(1)", "portal.example/listing/1", "file:///etc/passwd"])
    def test_url_must_be_a_web_link(self, url):
        with pytest.raises(ListingError, match="http"):
            Listing.from_dict({"url": url, "price_aed": 1_000_000, "evidence": "page"})

    def test_names_unknown_fields(self):
        with pytest.raises(ListingError, match="price"):
            Listing.from_dict({"url": "https://x.example/1", "price_aed": 1, "evidence": "page", "price": 2})

    @pytest.mark.parametrize(
        "field, value",
        [
            ("price_aed", -5),
            ("evidence", "rumour"),
            ("emirate", "doha"),
            ("completion", "derelict"),
            ("sale_type", "auction"),
            ("size_sqft", 0),
            ("benchmark_psf", -1),
            ("developer_tier", 4),
            ("handover", "someday"),
        ],
    )
    def test_rejects_bad_values(self, make_listing, field, value):
        with pytest.raises(ListingError):
            make_listing(**{field: value})


class TestPaymentPlan:
    def test_accepts_plan_that_sums_to_100(self, make_listing):
        plan = {"on_booking": 20, "during_construction": 40, "on_handover": 40}
        assert make_listing(completion="offplan", handover="2028-Q2", payment_plan=plan).payment_plan == plan

    def test_rejects_plan_that_does_not_sum_to_100(self, make_listing):
        with pytest.raises(ListingError, match="sum"):
            make_listing(payment_plan={"on_booking": 20, "on_handover": 70})

    def test_rejects_unknown_stage(self, make_listing):
        with pytest.raises(ListingError, match="stages"):
            make_listing(payment_plan={"on_booking": 20, "later": 80})

    def test_post_handover_share_needs_a_duration(self, make_listing):
        with pytest.raises(ListingError, match="post_handover_months"):
            make_listing(payment_plan={"on_booking": 40, "post_handover": 60})

    def test_all_stages_are_accepted(self, make_listing):
        plan = {stage: 25 for stage in PLAN_STAGES}
        listing = make_listing(payment_plan=plan, post_handover_months=24, handover="2028-Q1")
        assert set(listing.payment_plan) == set(PLAN_STAGES)
