from __future__ import annotations

import json

import httpx
import pytest

from tesco_mcp.tesco_api import (
    GRAPHQL_URL,
    SEARCH_BASE_URL,
    TescoNutrition,
    get_country_config,
    get_product,
    hydrate_products,
    parse_nutrition,
    search_products,
    search_tpnbs,
)


class TestParseNutrition:
    def test_full_chicken_breast_nutrition(self) -> None:
        raw = [
            {"name": "Typical Values", "value1": "Per 100g", "value2": None, "value3": None, "value4": None},
            {"name": "Energy", "value1": "449kJ / 106kcal", "value2": "null / null", "value3": None, "value4": None},
            {"name": "Fat", "value1": "1.1g", "value2": "", "value3": None, "value4": None},
            {"name": "Saturates", "value1": "0.3g", "value2": "", "value3": None, "value4": None},
            {"name": "Carbohydrate", "value1": "0g", "value2": "", "value3": None, "value4": None},
            {"name": "Sugars", "value1": "0g", "value2": "", "value3": None, "value4": None},
            {"name": "Fibre", "value1": "0g", "value2": "", "value3": None, "value4": None},
            {"name": "Protein", "value1": "24.0g", "value2": "", "value3": None, "value4": None},
            {"name": "Salt", "value1": "0.15g", "value2": "", "value3": None, "value4": None},
        ]
        result = parse_nutrition(raw)
        assert result.calories_kcal == 106.0
        assert result.protein_g == 24.0
        assert result.carbs_g == 0.0
        assert result.fat_g == 1.1
        assert result.fibre_g == 0.0
        assert result.sugar_g == 0.0
        assert result.salt_g == 0.15

    @pytest.mark.parametrize(
        ("name", "value", "field", "expected"),
        [
            ("Carbohydrates", "45.2g", "carbs_g", 45.2),
            ("Available Carbohydrate", "60.3g", "carbs_g", 60.3),
            ("Salt", "<0.01g", "salt_g", 0.01),
            ("Energy", "449kJ", "calories_kcal", None),
        ],
    )
    def test_variants(self, name: str, value: str, field: str, expected: float | None) -> None:
        nutrition = parse_nutrition([{"name": name, "value1": value}])
        assert getattr(nutrition, field) == expected

    def test_empty_rows_returns_all_none(self) -> None:
        assert parse_nutrition([]) == TescoNutrition()


class TestCountryConfig:
    def test_ireland_defaults(self) -> None:
        config = get_country_config("ie")
        assert config.region == "IE"
        assert config.language == "en-IE"
        assert config.currency == "EUR"

    def test_uk_config(self) -> None:
        config = get_country_config("uk")
        assert config.region == "UK"
        assert config.language == "en-GB"
        assert config.currency == "GBP"

    def test_unsupported_country_raises(self) -> None:
        with pytest.raises(ValueError, match="Unsupported country"):
            get_country_config("fr")


def _mock_client() -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url).startswith(SEARCH_BASE_URL):
            assert request.url.params["geo"] == "ie"
            return httpx.Response(
                200,
                json={
                    "ie": {
                        "ghs": {
                            "products": {
                                "results": [{"tpnb": 111}, {"tpnb": "222"}],
                                "totals": {"all": 2},
                            }
                        }
                    }
                },
            )

        if str(request.url) == GRAPHQL_URL:
            batch = json.loads(request.content.decode())
            payloads = {
                "111": _product_payload("111", "Chicken Breast", 6.15, "500", "G", "24.0g"),
                "222": _product_payload("222", "Chicken Mini Fillets", 5.00, "400", "G", "23.0g"),
            }
            return httpx.Response(
                200,
                json=[
                    {"data": {"product": payloads[item["variables"]["tpnb"]]}}
                    for item in batch
                ],
            )

        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    return httpx.Client(transport=httpx.MockTransport(handler))


def _product_payload(tpnb: str, title: str, price: float, pack_value: str, pack_units: str, protein: str) -> dict:
    return {
        "id": f"prod-{tpnb}",
        "gtin": f"gtin-{tpnb}",
        "title": title,
        "defaultImageUrl": f"https://example.com/{tpnb}.jpg",
        "price": {"actual": price, "unitPrice": price * 2, "unitOfMeasure": "kg"},
        "details": {
            "packSize": [{"value": pack_value, "units": pack_units}],
            "nutrition": [
                {"name": "Energy", "value1": "449kJ / 106kcal"},
                {"name": "Protein", "value1": protein},
                {"name": "Carbohydrate", "value1": "0g"},
                {"name": "Fat", "value1": "1.1g"},
                {"name": "Fibre", "value1": "0g"},
                {"name": "Sugars", "value1": "0g"},
                {"name": "Salt", "value1": "0.15g"},
            ],
            "ingredients": ["<p>Chicken breast</p>"],
        },
        "promotions": [{"description": "Clubcard Price"}],
    }


def test_search_tpnbs_uses_search_endpoint() -> None:
    with _mock_client() as client:
        tpnbs, total = search_tpnbs("chicken", count=2, client=client)
    assert tpnbs == [111, 222]
    assert total == 2


def test_hydrate_products_parses_price_pack_promo_and_nutrition() -> None:
    with _mock_client() as client:
        products = hydrate_products([111, 222], client=client)
    assert len(products) == 2
    first = products[0]
    assert first.tpnb == 111
    assert first.title == "Chicken Breast"
    assert first.price == 6.15
    assert first.price_eur == 6.15
    assert first.pack_size == "500G"
    assert first.promotions == ["Clubcard Price"]
    assert first.nutrition.protein_g == 24.0


def test_search_products_combines_search_and_hydration() -> None:
    with _mock_client() as client:
        result = search_products("chicken", count=2, client=client)
    assert result.query == "chicken"
    assert result.country == "ie"
    assert result.total == 2
    assert [product.tpnb for product in result.products] == [111, 222]


def test_get_product_returns_single_match() -> None:
    with _mock_client() as client:
        product = get_product(111, client=client)
    assert product is not None
    assert product.tpnb == 111


def test_hydrate_empty_list_returns_empty() -> None:
    assert hydrate_products([]) == []
