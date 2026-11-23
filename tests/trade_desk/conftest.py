"""Fixtures that build the example records in desk_examples, with overrides; DROP removes a field."""

import pytest

from desk_examples import ACCOUNT, SYMBOL, TRADE, merged
from trade_desk.account import Account
from trade_desk.spec import Symbol
from trade_desk.trade import Trade


@pytest.fixture
def make_symbol():
    def build(**overrides):
        return Symbol.from_dict(merged(SYMBOL, overrides))

    return build


@pytest.fixture
def make_account():
    def build(**overrides):
        return Account.from_dict(merged(ACCOUNT, overrides))

    return build


@pytest.fixture
def make_trade():
    def build(**overrides):
        return Trade.from_dict(merged(TRADE, overrides))

    return build


@pytest.fixture
def records(make_symbol, make_account, make_trade):
    """Symbol, account and trade, each with its own overrides."""

    def build(symbol=None, account=None, trade=None):
        return make_symbol(**(symbol or {})), make_account(**(account or {})), make_trade(**(trade or {}))

    return build
