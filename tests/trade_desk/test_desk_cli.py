"""The command line the agent calls: templates, check, size, atr and journal."""

import json

import pytest

from trade_desk.account import Account
from trade_desk.cli import ACCOUNT_TEMPLATE, CANDLES_TEMPLATE, JOURNAL_TEMPLATE, SYMBOL_TEMPLATE, TRADE_TEMPLATE, main
from trade_desk.journal import ClosedTrade, trades_from
from trade_desk.atr import candles_from
from trade_desk.spec import Symbol
from trade_desk.trade import Trade


@pytest.fixture
def output(capsys):
    def run(*args, code=0):
        assert main([str(arg) for arg in args]) == code
        return capsys.readouterr()

    return run


@pytest.fixture
def files(tmp_path):
    def write(name, content):
        path = tmp_path / name
        path.write_text(content if isinstance(content, str) else json.dumps(content), encoding="utf-8")
        return path

    write("symbol.json", SYMBOL_TEMPLATE)
    write("account.json", ACCOUNT_TEMPLATE)
    write("trade.json", TRADE_TEMPLATE)
    write("candles.json", CANDLES_TEMPLATE)
    write("journal.json", JOURNAL_TEMPLATE)
    write.dir = tmp_path
    return write


def check_args(files, *extra):
    return ["check", "--symbol", files.dir / "symbol.json", "--account", files.dir / "account.json", "--trade", files.dir / "trade.json", *extra]


class TestTemplates:
    def test_each_template_is_a_valid_record_that_shows_every_field(self):
        assert set(SYMBOL_TEMPLATE) == set(Symbol.__dataclass_fields__)
        assert set(ACCOUNT_TEMPLATE) == set(Account.__dataclass_fields__)
        assert set(TRADE_TEMPLATE) == set(Trade.__dataclass_fields__)
        Symbol.from_dict(dict(SYMBOL_TEMPLATE))
        Account.from_dict(dict(ACCOUNT_TEMPLATE))
        Trade.from_dict(dict(TRADE_TEMPLATE))
        assert set(JOURNAL_TEMPLATE[0]) == set(ClosedTrade.__dataclass_fields__)
        assert trades_from(JOURNAL_TEMPLATE) and len(candles_from(CANDLES_TEMPLATE)) >= 15

    @pytest.mark.parametrize("kind", ["symbol", "account", "trade", "journal", "candles"])
    def test_printed(self, output, kind):
        printed = json.loads(output("template", kind).out)
        expected = {"symbol": SYMBOL_TEMPLATE, "account": ACCOUNT_TEMPLATE, "trade": TRADE_TEMPLATE, "journal": JOURNAL_TEMPLATE, "candles": CANDLES_TEMPLATE}[kind]
        assert printed == expected


class TestCheck:
    def test_the_templates_together_are_a_go(self, files, output):
        data = json.loads(output(*check_args(files)).out)
        assert data["verdict"] == "go" and data["lots"] > 0

    def test_markdown(self, files, output):
        assert "**GO**" in output(*check_args(files, "--format", "md")).out

    def test_written_to_a_file(self, files, output):
        target = files.dir / "plan.md"
        printed = output(*check_args(files, "--format", "md", "--out", target)).out
        assert "wrote" in printed and "**GO**" in target.read_text(encoding="utf-8")
        assert not (files.dir / "plan.md.tmp").exists()

    def test_a_block_is_still_a_successful_run(self, files, output):
        files("account.json", dict(ACCOUNT_TEMPLATE, equity=ACCOUNT_TEMPLATE["day_start_balance"] * 0.9))
        assert json.loads(output(*check_args(files)).out)["verdict"] == "blocked"

    @pytest.mark.parametrize(
        "name, content, message",
        [
            ("trade.json", "{not json", "not valid JSON"),
            ("trade.json", '{"side": "buy", "side": "sell"}', "appears twice"),
            ("trade.json", dict(TRADE_TEMPLATE, symbol="EURUSD"), "EURUSD"),
            ("account.json", dict(ACCOUNT_TEMPLATE, risk_pct="1%"), "risk_pct"),
        ],
    )
    def test_bad_input_is_an_error_with_a_reason(self, files, output, name, content, message):
        files(name, content)
        result = output(*check_args(files), code=2)
        assert result.err.startswith("error:") and message in result.err

    def test_a_missing_file(self, files, output):
        args = check_args(files)
        args[2] = files.dir / "missing.json"
        assert output(*args, code=2).err.startswith("error:")


class TestSize:
    BASE = ["--equity", 10_000, "--risk", 0.5, "--side", "buy", "--entry", 4452.30, "--stop", 4440.30]

    def test_json(self, files, output):
        files("symbol.json", dict(SYMBOL_TEMPLATE, commission_per_lot=7.0, tick_value=1.0, contract_size=100, tick_size=0.01, volume_min=0.01, volume_step=0.01, volume_max=100))
        data = json.loads(output("size", "--symbol", files.dir / "symbol.json", *self.BASE, "--target", 4476.30, "--json").out)
        assert data["lots"] == 0.04 and data["risk"] == 48.28 and data["r_multiple"] == pytest.approx(1.98, abs=0.005)

    def test_text(self, files, output):
        text = output("size", "--symbol", files.dir / "symbol.json", *self.BASE).out
        assert " lots" in text and "USD" in text

    def test_a_stop_on_the_wrong_side(self, files, output):
        args = ["size", "--symbol", files.dir / "symbol.json", *self.BASE]
        args[args.index("--stop") + 1] = 4460.0
        assert "stop" in output(*args, code=2).err


class TestAtr:
    def test_value(self, files, output):
        data = json.loads(output("atr", "--candles", files.dir / "candles.json").out)
        assert data["period"] == 14 and data["method"] == "sma" and data["atr"] > 0
        assert data["bars"] == len(CANDLES_TEMPLATE) and data["last"]

    def test_with_a_stop(self, files, output):
        data = json.loads(output("atr", "--candles", files.dir / "candles.json", "--period", 3, "--method", "wilder",
                                 "--multiple", 1.5, "--side", "sell", "--entry", 4452.30, "--tick-size", 0.01).out)
        assert data["method"] == "wilder" and data["stop"] > 4452.30

    def test_a_stop_needs_a_side_and_an_entry(self, files, output):
        assert "--side" in output("atr", "--candles", files.dir / "candles.json", "--multiple", 1.5, code=2).err

    def test_an_object_holding_the_candles(self, files, output):
        files("wrapped.json", {"candles": CANDLES_TEMPLATE})
        assert json.loads(output("atr", "--candles", files.dir / "wrapped.json").out)["atr"] > 0


class TestJournal:
    def test_json(self, files, output):
        data = json.loads(output("journal", "--trades", files.dir / "journal.json", "--start-balance", 10_000).out)
        assert data["trades"] == len(JOURNAL_TEMPLATE) and data["max_drawdown_pct"] is not None

    def test_markdown(self, files, output):
        assert "Win rate" in output("journal", "--trades", files.dir / "journal.json", "--format", "md").out

    def test_an_object_holding_the_trades(self, files, output):
        files("wrapped.json", {"trades": JOURNAL_TEMPLATE})
        assert json.loads(output("journal", "--trades", files.dir / "wrapped.json").out)["trades"] == len(JOURNAL_TEMPLATE)


def test_help_lists_every_command(capsys):
    with pytest.raises(SystemExit) as stop:
        main(["--help"])
    assert stop.value.code == 0
    text = capsys.readouterr().out
    for command in ("template", "check", "size", "atr", "journal"):
        assert command in text
