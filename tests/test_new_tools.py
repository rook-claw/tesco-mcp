"""Tests for v1.1 tools: promotions, alternatives, meal cost, weekly shop."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from tesco_mcp.models import TescoNutrition, TescoProduct, TescoSearchResult
from tesco_mcp.server import (
    _parse_csv_items,
    _parse_quantity_items,
    _cheapest_product,
    _empty_nutrition_total,
    _add_nutrition,
    _promotion_row,
    _alternative_row,
)


# ---------------------------------------------------------------------------
# Helper unit tests
# ---------------------------------------------------------------------------


class TestParseCsvItems:
    def test_basic_split(self) -> None:
        assert _parse_csv_items("chicken, rice, broccoli") == ["chicken", "rice", "broccoli"]

    def test_strips_whitespace(self) -> None:
        assert _parse_csv_items("  eggs ,  milk  ") == ["eggs", "milk"]

    def test_empty_string(self) -> None:
        assert _parse_csv_items("") == []

    def test_trailing_comma(self) -> None:
        assert _parse_csv_items("chicken,") == ["chicken"]


class TestParseQuantityItems:
    def test_basic_quantity(self) -> None:
        items = _parse_quantity_items("chicken breast x2, rice x1")
        assert len(items) == 2
        assert items[0] == {"name": "chicken breast", "quantity": 2.0}
        assert items[1] == {"name": "rice", "quantity": 1.0}

    def test_no_quantity_defaults_to_one(self) -> None:
        items = _parse_quantity_items("eggs, milk")
        assert items[0] == {"name": "eggs", "quantity": 1.0}

    def test_decimal_quantity(self) -> None:
        items = _parse_quantity_items("butter x0.5")
        assert items[0]["quantity"] == 0.5

    def test_empty_string(self) -> None:
        assert _parse_quantity_items("") == []


class TestCheapestProduct:
    def test_finds_cheapest(self) -> None:
        products = [
            TescoProduct(tpnb=1, title="Expensive", price=5.0),
            TescoProduct(tpnb=2, title="Cheap", price=2.0),
            TescoProduct(tpnb=3, title="Mid", price=3.5),
        ]
        assert _cheapest_product(products).tpnb == 2

    def test_empty_list(self) -> None:
        assert _cheapest_product([]) is None

    def test_skips_zero_price(self) -> None:
        products = [
            TescoProduct(tpnb=1, title="Free", price=0.0),
            TescoProduct(tpnb=2, title="Real", price=4.0),
        ]
        assert _cheapest_product(products).tpnb == 2


class TestNutritionHelpers:
    def test_empty_nutrition_total(self) -> None:
        total = _empty_nutrition_total()
        assert all(v == 0.0 for v in total.values())

    def test_add_nutrition(self) -> None:
        total = _empty_nutrition_total()
        n = TescoNutrition(calories_kcal=100, protein_g=25, carbs_g=10, fat_g=5)
        _add_nutrition(total, n)
        assert total["calories_kcal"] == 100.0
        assert total["protein_g"] == 25.0

    def test_add_nutrition_with_none(self) -> None:
        total = _empty_nutrition_total()
        n = TescoNutrition(calories_kcal=None, protein_g=10)
        _add_nutrition(total, n)
        assert total["calories_kcal"] == 0.0
        assert total["protein_g"] == 10.0


class TestRowBuilders:
    def _make_product(self, **kwargs) -> TescoProduct:
        defaults = {"tpnb": 123, "title": "Test Product", "price": 3.50, "currency": "EUR"}
        defaults.update(kwargs)
        return TescoProduct(**defaults)

    def test_promotion_row(self) -> None:
        p = self._make_product(promotions=["Buy 2 for €5"])
        row = _promotion_row(p)
        assert row["promotions"] == ["Buy 2 for €5"]
        assert row["price"] == 3.50

    def test_alternative_row_savings(self) -> None:
        p = self._make_product(price=2.50)
        row = _alternative_row(p, baseline_price=5.00)
        assert row["savings_vs_baseline"] == 2.50

    def test_alternative_row_more_expensive(self) -> None:
        p = self._make_product(price=6.00)
        row = _alternative_row(p, baseline_price=5.00)
        assert row["savings_vs_baseline"] == -1.00
