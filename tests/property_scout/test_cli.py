import json

import pytest

from property_scout.cli import BRIEF_TEMPLATE, LISTING_TEMPLATE, main
from property_scout.brief import Brief
from property_scout.listing import Listing


@pytest.fixture
def files(tmp_path):
    brief = tmp_path / "brief.json"
    listings = tmp_path / "listings.json"
    brief.write_text(json.dumps(BRIEF_TEMPLATE))
    listings.write_text(json.dumps([LISTING_TEMPLATE]))
    return brief, listings, tmp_path


class TestTemplates:
    def test_templates_are_valid_inputs(self):
        assert Brief.from_dict(dict(BRIEF_TEMPLATE)).budget_max == BRIEF_TEMPLATE["budget_max"]
        assert Listing.from_dict(dict(LISTING_TEMPLATE)).url == LISTING_TEMPLATE["url"]

    @pytest.mark.parametrize("kind", ["brief", "listings"])
    def test_template_command_prints_json(self, capsys, kind):
        assert main(["template", kind]) == 0
        assert json.loads(capsys.readouterr().out)


class TestScore:
    def test_json_to_stdout(self, files, capsys):
        brief, listings, _ = files
        assert main(["score", "--brief", str(brief), "--listings", str(listings), "--today", "2026-11-19"]) == 0
        data = json.loads(capsys.readouterr().out)
        assert data["as_of"] == "2026-11-19"
        assert data["counts"]["received"] == 1

    def test_accepts_an_object_wrapping_the_listings(self, files, capsys):
        brief, listings, _ = files
        listings.write_text(json.dumps({"listings": [LISTING_TEMPLATE]}))
        assert main(["score", "--brief", str(brief), "--listings", str(listings)]) == 0
        assert json.loads(capsys.readouterr().out)["counts"]["received"] == 1

    @pytest.mark.parametrize("fmt, marker", [("html", "<!doctype html>"), ("md", "# ")])
    def test_writes_reports_to_a_file(self, files, capsys, fmt, marker):
        brief, listings, tmp_path = files
        out = tmp_path / f"shortlist.{fmt}"
        code = main(["score", "--brief", str(brief), "--listings", str(listings), "--format", fmt, "--lang", "ru", "--out", str(out)])
        assert code == 0
        assert out.read_text(encoding="utf-8").startswith(marker)
        assert str(out) in capsys.readouterr().out

    def test_bad_brief_is_a_usage_error_not_a_traceback(self, files, capsys):
        brief, listings, _ = files
        brief.write_text(json.dumps({"budget": 1}))
        assert main(["score", "--brief", str(brief), "--listings", str(listings)]) == 2
        assert "error:" in capsys.readouterr().err

    def test_bad_listing_names_the_problem(self, files, capsys):
        brief, listings, _ = files
        listings.write_text(json.dumps([{"url": "https://x.example/1", "price_aed": 1, "cost": 2}]))
        assert main(["score", "--brief", str(brief), "--listings", str(listings)]) == 2
        assert "cost" in capsys.readouterr().err

    def test_listings_must_be_a_list(self, files, capsys):
        brief, listings, _ = files
        listings.write_text(json.dumps({"items": []}))
        assert main(["score", "--brief", str(brief), "--listings", str(listings)]) == 2

    def test_missing_file_and_broken_json_are_reported(self, files, capsys):
        brief, listings, tmp_path = files
        assert main(["score", "--brief", str(tmp_path / "nope.json"), "--listings", str(listings)]) == 2
        listings.write_text("{not json")
        assert main(["score", "--brief", str(brief), "--listings", str(listings)]) == 2


class TestOtherCommands:
    def test_plan_prints_steps(self, files, capsys):
        brief, _, _ = files
        assert main(["plan", "--brief", str(brief)]) == 0
        assert {step["step"] for step in json.loads(capsys.readouterr().out)} >= {"listings", "leads"}

    def test_costs_text_and_json_agree(self, capsys):
        args = ["costs", "--price", "2000000", "--emirate", "dubai", "--sale-type", "resale"]
        assert main(args + ["--json"]) == 0
        data = json.loads(capsys.readouterr().out)
        assert data["total_outlay_aed"] == pytest.approx(2_000_000 + data["total_costs_aed"])
        assert main(args) == 0
        assert f"{data['total_outlay_aed']:,.0f}" in capsys.readouterr().out

    def test_comps_reports_the_median(self, tmp_path, capsys):
        rows = tmp_path / "rows.json"
        rows.write_text(json.dumps([{"price_aed": 1_500_000, "size_sqft": 750}, {"price_aed": 1_650_000, "size_sqft": 750}, {"price_aed": 1_800_000, "size_sqft": 750}]))
        assert main(["comps", "--rows", str(rows), "--size", "750", "--today", "2026-11-19"]) == 0
        data = json.loads(capsys.readouterr().out)
        assert data["median_psf"] == pytest.approx(2200)
        assert data["thin"] and data["note"]

    def test_comps_rejects_a_non_list(self, tmp_path, capsys):
        rows = tmp_path / "rows.json"
        rows.write_text("{}")
        assert main(["comps", "--rows", str(rows)]) == 2
