import json

import pytest

from property_scout.brief import Brief
from property_scout.cli import BRIEF_TEMPLATE, OFFPLAN_EXAMPLE, READY_EXAMPLE, main
from property_scout.comps import MIN_COMPS
from property_scout.costs import LTV_CAP_HOME, LTV_CAP_INVESTMENT, SCHEDULES
from property_scout.listing import Listing
from property_scout.messages import UI

EXAMPLES = [READY_EXAMPLE, OFFPLAN_EXAMPLE]
COSTS = ["costs", "--price", "2000000", "--emirate", "dubai", "--sale-type", "resale"]


@pytest.fixture
def files(tmp_path):
    brief = tmp_path / "brief.json"
    listings = tmp_path / "listings.json"
    brief.write_text(json.dumps(BRIEF_TEMPLATE))
    listings.write_text(json.dumps(EXAMPLES))
    return brief, listings, tmp_path


@pytest.fixture
def output(capsys):
    def run(*args, code=0):
        assert main(list(args)) == code
        return capsys.readouterr()

    return run


class TestTemplates:
    def test_templates_are_valid_inputs_that_show_every_field(self):
        assert Brief.from_dict(dict(BRIEF_TEMPLATE)).budget_max == BRIEF_TEMPLATE["budget_max"]
        assert set(BRIEF_TEMPLATE) == set(Brief.__dataclass_fields__)
        for example in EXAMPLES:
            assert Listing.from_dict(dict(example)).url == example["url"]
            assert set(example) == set(Listing.__dataclass_fields__)

    def test_the_examples_cover_a_ready_resale_and_an_off_plan_launch(self):
        assert (READY_EXAMPLE["completion"], READY_EXAMPLE["sale_type"]) == ("ready", "resale")
        assert (OFFPLAN_EXAMPLE["completion"], OFFPLAN_EXAMPLE["sale_type"]) == ("offplan", "primary")
        assert OFFPLAN_EXAMPLE["payment_plan"] and OFFPLAN_EXAMPLE["register_completion"]

    def test_template_command_prints_json(self, output):
        assert json.loads(output("template", "brief").out) == BRIEF_TEMPLATE
        assert json.loads(output("template", "listings").out) == EXAMPLES


class TestScore:
    def test_json_to_stdout(self, files, output):
        brief, listings, _ = files
        data = json.loads(output("score", "--brief", str(brief), "--listings", str(listings), "--today", "2026-11-20").out)
        assert data["as_of"] == "2026-11-20"
        assert data["counts"] == {"received": 2, "unique": 2, "ranked": 2, "shortlisted": 2, "rejected": 0}
        assert {row["url"] for row in data["ranked"]} == {READY_EXAMPLE["url"], OFFPLAN_EXAMPLE["url"]}

    def test_accepts_an_object_wrapping_the_listings(self, files, output):
        brief, listings, _ = files
        listings.write_text(json.dumps({"listings": EXAMPLES}))
        assert json.loads(output("score", "--brief", str(brief), "--listings", str(listings)).out)["counts"]["received"] == 2

    @pytest.mark.parametrize("fmt, marker", [("html", "<!doctype html>"), ("md", "# ")])
    def test_writes_reports_to_a_file(self, files, output, fmt, marker):
        brief, listings, tmp_path = files
        out = tmp_path / f"shortlist.{fmt}"
        printed = output("score", "--brief", str(brief), "--listings", str(listings), "--format", fmt, "--lang", "ru", "--out", str(out)).out
        assert out.read_text(encoding="utf-8").startswith(marker)
        assert str(out) in printed

    def test_top_limits_the_report(self, files, output):
        brief, listings, _ = files
        data = json.loads(output("score", "--brief", str(brief), "--listings", str(listings), "--top", "1").out)
        assert len(data["ranked"]) == 1

    def test_bad_brief_is_a_usage_error_not_a_traceback(self, files, output):
        brief, listings, _ = files
        brief.write_text(json.dumps({"budget": 1}))
        assert "error:" in output("score", "--brief", str(brief), "--listings", str(listings), code=2).err

    def test_a_bad_listing_is_named_by_its_position_and_field(self, files, output):
        brief, listings, _ = files
        listings.write_text(json.dumps([READY_EXAMPLE, {"url": "https://x.example/1", "price_aed": 1, "evidence": "page", "cost": 2}]))
        err = output("score", "--brief", str(brief), "--listings", str(listings), code=2).err
        assert "listing 2" in err and "cost" in err and "Traceback" not in err

    def test_a_wrongly_typed_value_is_refused_not_coerced(self, files, output):
        brief, listings, _ = files
        listings.write_text(json.dumps([{**READY_EXAMPLE, "price_aed": "1,850,000"}]))
        assert "price_aed must be a number" in output("score", "--brief", str(brief), "--listings", str(listings), code=2).err

    def test_listings_must_be_a_list(self, files, output):
        brief, listings, _ = files
        listings.write_text(json.dumps({"items": []}))
        assert "array" in output("score", "--brief", str(brief), "--listings", str(listings), code=2).err

    def test_missing_file_and_broken_json_are_reported(self, files, output):
        brief, listings, tmp_path = files
        assert "nope.json" in output("score", "--brief", str(tmp_path / "nope.json"), "--listings", str(listings), code=2).err
        listings.write_text("{not json")
        err = output("score", "--brief", str(brief), "--listings", str(listings), code=2).err
        assert "listings.json is not valid JSON" in err

    @pytest.mark.parametrize("option, value", [("--today", "20.11.2026"), ("--today", "2026-13-01"), ("--top", "0"), ("--top", "two")])
    def test_a_bad_option_is_one_clear_line(self, files, capsys, option, value):
        brief, listings, _ = files
        with pytest.raises(SystemExit) as stop:
            main(["score", "--brief", str(brief), "--listings", str(listings), option, value])
        assert stop.value.code == 2
        assert f"argument {option}" in capsys.readouterr().err


class TestCosts:
    def test_text_and_json_agree(self, output):
        data = json.loads(output(*COSTS, "--json").out)
        assert data["total_outlay_aed"] == pytest.approx(2_000_000 + data["total_costs_aed"])
        assert data["own_funds_aed"] == data["total_outlay_aed"] and data["loan_aed"] == 0 and data["notes"] == []
        assert f"{data['total_outlay_aed']:,.0f}" in output(*COSTS).out

    def test_a_loan_is_cut_to_the_ceiling_and_own_funds_are_shown(self, output):
        asked = ["--financing", "mortgage", "--ltv", "0.75"]
        investor = json.loads(output(*COSTS, *asked, "--json").out)
        home = json.loads(output(*COSTS, *asked, "--first-home", "--json").out)
        assert investor["loan_to_value_used"] == pytest.approx(LTV_CAP_INVESTMENT) and len(investor["notes"]) == 1
        assert home["loan_to_value_used"] == pytest.approx(0.75) and home["loan_to_value_cap"] == LTV_CAP_HOME and home["notes"] == []
        assert home["own_funds_aed"] == pytest.approx(home["total_outlay_aed"] - home["loan_aed"])
        text = output(*COSTS, *asked).out
        assert UI["en"]["own_funds_total"] in text and "\n! " in text

    def test_nationality_community_and_waiver_reach_the_engine(self, output):
        def total(*args):
            return json.loads(output("costs", "--price", "2000000", "--json", *args).out)["total_costs_aed"]

        assert total("--emirate", "sharjah", "--nationality", "gcc") < total("--emirate", "sharjah")
        assert total("--emirate", "abu_dhabi", "--community", "Al Reem Island") < total("--emirate", "abu_dhabi")
        primary = ["--emirate", "dubai", "--completion", "offplan", "--sale-type", "primary"]
        assert total(*primary) - total(*primary, "--waived") == pytest.approx(2_000_000 * SCHEDULES["dubai"].transfer_rate)

    def test_a_partly_published_schedule_says_so(self, output):
        printed = output("costs", "--price", "900000", "--emirate", "ajman", "--lang", "ru").out
        assert "\n! " in printed and "AED" in printed

    @pytest.mark.parametrize("option, value", [("--price", "0"), ("--price", "-5"), ("--price", "nan"), ("--price", "2m"), ("--ltv", "75"), ("--ltv", "1"), ("--ltv", "0")])
    def test_refuses_figures_that_make_no_sense(self, capsys, option, value):
        args = [arg for arg in COSTS if arg not in ("--price", "2000000")] if option == "--price" else list(COSTS)
        with pytest.raises(SystemExit):
            main(args + [option, value])
        assert f"argument {option}" in capsys.readouterr().err


class TestOtherCommands:
    def test_plan_prints_steps(self, files, output):
        brief, _, _ = files
        plan = json.loads(output("plan", "--brief", str(brief)).out)
        assert {step["step"] for step in plan} >= {"listings", "new_projects", "sold_benchmark", "leads"}

    def test_comps_reports_the_median_the_span_and_what_is_weak(self, tmp_path, output):
        rows = tmp_path / "rows.json"
        rows.write_text(json.dumps([
            {"price_aed": 1_500_000, "size_sqft": 750, "date": "2026-10-01", "project": "A"},
            {"price_aed": 1_650_000, "size_sqft": 750, "date": "2026-11-02", "project": "A"},
            {"price_aed": 1_800_000, "size_sqft": 750, "project": "B"},
        ]))
        data = json.loads(output("comps", "--rows", str(rows), "--size", "750", "--today", "2026-11-19").out)
        assert data["median_psf"] == pytest.approx(2200)
        assert (data["first_date"], data["last_date"]) == ("2026-10-01", "2026-11-02")
        assert data["thin"] and data["largest_project_share"] == pytest.approx(2 / 3)
        assert len(data["notes"]) == 2 and str(MIN_COMPS) in data["notes"][0]

    def test_comps_can_keep_new_leases_only(self, tmp_path, output):
        rows = tmp_path / "rows.json"
        rows.write_text(json.dumps([{"price_aed": 120_000, "size_sqft": 750, "contract": "new"}, {"price_aed": 90_000, "size_sqft": 750, "contract": "renewal"}]))
        assert json.loads(output("comps", "--rows", str(rows)).out)["used"] == 2
        kept = json.loads(output("comps", "--rows", str(rows), "--new-leases").out)
        assert kept["used"] == 1 and kept["dropped"]["contract"] == 1

    def test_comps_rejects_a_non_list_and_names_a_bad_row(self, tmp_path, output):
        rows = tmp_path / "rows.json"
        rows.write_text("{}")
        assert "array" in output("comps", "--rows", str(rows), code=2).err
        rows.write_text(json.dumps([{"price_aed": "1.5m", "size_sqft": 750}]))
        assert "row 1" in output("comps", "--rows", str(rows), code=2).err

    def test_a_command_is_required(self, capsys):
        with pytest.raises(SystemExit):
            main([])
