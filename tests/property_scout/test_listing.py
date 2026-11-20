import pytest

from property_scout.fields import LONG_TEXT, MAX_TEXT
from property_scout.listing import ANALYST_CAPS, EVIDENCE, MAX_LABEL, MIN_PERMIT_DIGITS, PLAN_STAGES, REQUIRED, Listing, ListingError

MINIMAL = {"url": "https://x.example/1", "price_aed": 1_000_000, "evidence": "page"}


class TestListingParsing:
    def test_price_per_sqft(self, make_listing):
        assert make_listing(price_aed=1_500_000, size_sqft=750).price_psf == 2000

    def test_price_per_sqft_needs_size(self, make_listing):
        assert make_listing(size_sqft=None).price_psf is None

    def test_normalises_choices_and_tags(self, make_listing):
        listing = make_listing(completion="Off-Plan", emirate="Ras Al Khaimah", tags=["Sea View", " "], property_type="Apartments")
        assert listing.completion == "offplan" and listing.offplan
        assert listing.emirate == "ras_al_khaimah"
        assert listing.tags == ["sea_view"]
        assert listing.property_type == "apartment"

    @pytest.mark.parametrize("level", EVIDENCE)
    def test_accepts_every_evidence_level(self, make_listing, level):
        assert make_listing(evidence=level.upper()).evidence == level

    def test_label_prefers_building_then_community(self, make_listing):
        assert make_listing().label == "Marina Gate 1, Dubai Marina"

    def test_label_falls_back_to_title_then_url(self):
        titled = Listing.from_dict({**MINIMAL, "title": "Sea view flat"})
        assert titled.label == "Sea view flat"
        assert Listing.from_dict(MINIMAL).label == MINIMAL["url"]

    def test_a_timestamp_is_kept_as_its_date(self, make_listing):
        assert make_listing(observed_on="2026-11-19T07:15:00+04:00").observed_on == "2026-11-19"

    def test_the_register_date_overrides_the_advertised_handover(self, make_listing):
        advert_only = make_listing(completion="offplan", handover="2028-Q2")
        both = make_listing(completion="offplan", handover="2028-Q2", register_completion="2029-Q1")
        assert advert_only.scheduled_handover == "2028-Q2"
        assert both.scheduled_handover == "2029-Q1"

    def test_blank_text_is_no_value(self, make_listing):
        listing = make_listing(developer="  ", permit_number="", sub_community=None)
        assert listing.developer is None and listing.permit_number is None and listing.sub_community is None


class TestListingValidation:
    @pytest.mark.parametrize("missing", REQUIRED)
    def test_requires_url_price_and_evidence_level(self, missing):
        data = dict(MINIMAL)
        del data[missing]
        with pytest.raises(ListingError, match=missing):
            Listing.from_dict(data)

    def test_rejects_non_object(self):
        with pytest.raises(ListingError, match="JSON object"):
            Listing.from_dict("https://x.example/1")

    @pytest.mark.parametrize("url", ["javascript:alert(1)", "portal.example/listing/1", "file:///etc/passwd"])
    def test_url_must_be_a_web_link(self, url):
        with pytest.raises(ListingError, match="http"):
            Listing.from_dict({**MINIMAL, "url": url})

    def test_names_unknown_fields(self):
        with pytest.raises(ListingError, match="'price'"):
            Listing.from_dict({**MINIMAL, "price": 2})

    def test_the_error_names_the_listing(self):
        with pytest.raises(ListingError, match=r"https://x.example/1: size_sqft must be a number"):
            Listing.from_dict({**MINIMAL, "size_sqft": "750 sqft"})

    @pytest.mark.parametrize(
        "field, value",
        [
            ("price_aed", -5),
            ("price_aed", "1,800,000"),
            ("price_aed", True),
            ("evidence", "rumour"),
            ("emirate", "doha"),
            ("completion", "derelict"),
            ("sale_type", "auction"),
            ("size_sqft", 0),
            ("bedrooms", 1.5),
            ("bedrooms", "2"),
            ("bedrooms", 40),
            ("benchmark_psf", -1),
            ("benchmark_count", -1),
            ("rent_count", 2.5),
            ("developer_tier", 4),
            ("developer_tier", 0),
            ("handover", "someday"),
            ("register_completion", "soon"),
            ("register_progress_pct", 101),
            ("register_inspected_on", "05.10.2026"),
            ("observed_on", "yesterday"),
            ("verified", "yes"),
            ("registration_verified", 1),
            ("from_price", "true"),
            ("tags", "sea view"),
            ("sources", ["https://x.example"]),
            ("sources", {"sold": 5}),
            ("title", "two\nlines"),
            ("post_handover_months", -1),
            ("analyst_cap", "shortlist"),
            ("analyst_note", "confirmed on the phone"),
            ("completion", "resale"),
            ("property_type", "vila"),
            ("property_type", "apartment 1br"),
            ("handover", "3027-Q4"),
            ("register_started", "long ago"),
            ("price_aed", 0.004),
            ("price_aed", 10 ** 400),
            ("size_sqft", 5e-324),
            ("price_corroborated", "yes"),
            ("observed_on", "2026-11-19 or thereabouts"),
        ],
    )
    def test_rejects_bad_values(self, make_listing, field, value):
        with pytest.raises(ListingError):
            make_listing(**{field: value})

    @pytest.mark.parametrize(
        "url",
        [
            "https://x.example/1><img src=x onerror=alert(1)>",
            "https://x.example/a b",
            "https://x.example/a'onmouseover='x",
            'https://x.example/a"b',
            "https://x.example/a`b",
            "https://[2001:db8::1/listing/1",
            "https:///no-host",
        ],
    )
    def test_a_link_must_be_one_a_report_can_print(self, url):
        with pytest.raises(ListingError, match="well-formed web address"):
            Listing.from_dict({**MINIMAL, "url": url})
        with pytest.raises(ListingError, match="well-formed web address"):
            Listing.from_dict({**MINIMAL, "sources": {"sold": url}})

    def test_a_source_may_be_plain_text_but_needs_a_one_line_name(self):
        assert Listing.from_dict({**MINIMAL, "sources": {"broker": "phone call, 19 November"}}).sources == {"broker": "phone call, 19 November"}
        for name in ("", "two\nlines", "x" * (MAX_TEXT + 1)):
            with pytest.raises(ListingError, match="sources"):
                Listing.from_dict({**MINIMAL, "sources": {name: "https://x.example/sold"}})

    @pytest.mark.parametrize("placeholder", ["N/A", "-", "none", "0", "?", "not shown", "1234"])
    def test_a_permit_number_is_the_number_or_nothing(self, placeholder):
        with pytest.raises(ListingError, match="permit_number must be the number as the page prints it"):
            Listing.from_dict({**MINIMAL, "permit_number": placeholder})
        assert Listing.from_dict({**MINIMAL, "permit_number": "7" * MIN_PERMIT_DIGITS}).permit_number

    @pytest.mark.parametrize("placeholder", ["N/A", "0000", "-"])
    def test_a_project_number_is_the_number_or_nothing(self, placeholder):
        with pytest.raises(ListingError, match="project_number"):
            Listing.from_dict({**MINIMAL, "project_number": placeholder})
        assert Listing.from_dict({**MINIMAL, "project_number": "89"}).project_number == "89"

    def test_notes_and_bases_have_room_for_a_paragraph(self):
        long = "x" * LONG_TEXT
        listing = Listing.from_dict({**MINIMAL, "notes": long, "benchmark_basis": long, "rent_basis": long, "ready_benchmark_basis": long})
        assert len(listing.notes) == LONG_TEXT
        with pytest.raises(ListingError, match=f"notes is longer than {LONG_TEXT}"):
            Listing.from_dict({**MINIMAL, "notes": long + "x"})
        with pytest.raises(ListingError, match=f"title is longer than {MAX_TEXT}"):
            Listing.from_dict({**MINIMAL, "title": "x" * (MAX_TEXT + 1)})

    def test_the_label_in_an_error_cannot_carry_markup_or_a_second_line(self):
        with pytest.raises(ListingError) as caught:
            Listing.from_dict({"url": "https://x.example/1\nerror: listing 7 is fine\x1b[31m", "price_aed": 1_000_000, "evidence": "page"})
        message = str(caught.value)
        assert "\n" not in message and "\x1b" not in message
        with pytest.raises(ListingError) as caught:
            Listing.from_dict({"title": "t" * 500, "evidence": "page"})
        assert len(str(caught.value)) < MAX_LABEL + 60

    @pytest.mark.parametrize("kind, filed", [("Semi-detached villa", "villa"), ("Bungalow", "villa"), ("Hotel Apartment", "apartment")])
    def test_common_portal_types_are_read_as_the_engine_types(self, make_listing, kind, filed):
        assert make_listing(property_type=kind).property_type == filed

    @pytest.mark.parametrize("cap", ANALYST_CAPS)
    def test_an_analyst_cap_needs_its_reason(self, make_listing, cap):
        with pytest.raises(ListingError, match="analyst_note"):
            make_listing(analyst_cap=cap)
        assert make_listing(analyst_cap=cap, analyst_note="floor plan shows a studio").analyst_cap == cap


class TestPaymentPlan:
    def test_accepts_plan_that_sums_to_100(self, make_listing):
        plan = {"on_booking": 20, "during_construction": 40, "on_handover": 40}
        assert make_listing(completion="offplan", handover="2028-Q2", payment_plan=plan).payment_plan == plan

    def test_rejects_plan_that_does_not_sum_to_100(self, make_listing):
        with pytest.raises(ListingError, match="sum to 100"):
            make_listing(payment_plan={"on_booking": 20, "on_handover": 70})

    def test_rejects_unknown_stage(self, make_listing):
        with pytest.raises(ListingError, match="payment_plan stage"):
            make_listing(payment_plan={"on_booking": 20, "later": 80})

    @pytest.mark.parametrize("share", ["20", -5, 120, None])
    def test_rejects_shares_that_are_not_percentages(self, make_listing, share):
        with pytest.raises(ListingError):
            make_listing(payment_plan={"on_booking": share, "on_handover": 80})

    def test_a_post_handover_share_may_come_without_its_period(self, make_listing):
        listing = make_listing(payment_plan={"on_booking": 40, "post_handover": 60})
        assert listing.payment_plan["post_handover"] == 60 and listing.post_handover_months == 0

    def test_all_stages_are_accepted(self, make_listing):
        plan = {stage: 25 for stage in PLAN_STAGES}
        listing = make_listing(payment_plan=plan, post_handover_months=24, handover="2028-Q1")
        assert set(listing.payment_plan) == set(PLAN_STAGES)
