from datetime import date

import pytest

from property_scout.brief import Brief
from property_scout.listing import Listing

TODAY = date(2026, 11, 19)


@pytest.fixture
def today():
    return TODAY


@pytest.fixture
def make_brief():
    def build(**overrides):
        data = {"budget_max": 2_500_000, "emirates": ["dubai"]}
        data.update(overrides)
        return Brief.from_dict(data)

    return build


@pytest.fixture
def make_listing():
    def build(**overrides):
        data = {
            "url": "https://portal.example/listing/1",
            "price_aed": 1_800_000,
            "evidence": "page",
            "emirate": "dubai",
            "community": "Dubai Marina",
            "building": "Marina Gate 1",
            "property_type": "apartment",
            "bedrooms": 1,
            "size_sqft": 750,
            "completion": "ready",
            "sale_type": "resale",
        }
        data.update(overrides)
        return Listing.from_dict(data)

    return build
