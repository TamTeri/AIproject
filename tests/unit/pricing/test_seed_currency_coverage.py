"""system-016: adding an enabled currency to the seed without a hand-derived purchase expectation fails."""

import importlib.util
import json
from pathlib import Path

import pytest

SEED = json.loads((Path(__file__).parents[3] / "seed" / "catalog.json").read_text(encoding="utf-8"))
ENABLED = {c["code"] for c in SEED["currencies"] if c["enabled"]}
ZERO_DECIMAL = {c["code"] for c in SEED["currencies"] if c["minor_unit"] == 0}


@pytest.mark.requirement("system-016")
def test_every_enabled_seed_currency_has_a_purchase_expectation():
    spec = importlib.util.spec_from_file_location(
        "multicurrency", Path(__file__).parents[2] / "integration" / "test_multicurrency.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert ENABLED == set(module.EXPECTED)
    assert "JPY" in ZERO_DECIMAL  # a zero-decimal currency must stay represented
