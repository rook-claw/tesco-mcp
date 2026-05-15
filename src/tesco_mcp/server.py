"""FastMCP server exposing Tesco IE/UK grocery shopping tools."""

from __future__ import annotations

import json
import re
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP

from .tesco_api import get_product as api_get_product
from .tesco_api import search_products as api_search_products

mcp = FastMCP("tesco", dependencies=["httpx", "pydantic"])

SortBy = Literal["price", "protein", "calories", "protein_per_euro"]
_QUANTITY_RE = re.compile(r"^(?P<name>.+?)\s+x\s*(?P<quantity>\d+(?:\.\d+)?)$", re.IGNORECASE)


def _json(data: Any) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False)


def _product_to_dict(product: Any) -> dict[str, Any]:
    return product.model_dump(mode="json")


def _require_product(tpnb: int, country: str = "ie") -> Any:
    product = api_get_product(tpnb, country=country)
    if product is None:
        raise ValueError(f"No Tesco product found for TPNB {tpnb}")
    return product


@mcp.tool()
async def search_products(query: str, count: int = 10, country: str = "ie") -> str:
    """Search Tesco groceries by name. Returns products with prices, nutrition, pack size, and promotions."""
    result = api_search_products(query, count=count, country=country)
    return _json(result.model_dump(mode="json"))


@mcp.tool()
async def get_product(tpnb: int, country: str = "ie") -> str:
    """Get full Tesco product details by TPNB ID, including price, promotions, ingredients, and nutrition."""
    product = _require_product(tpnb, country=country)
    return _json(_product_to_dict(product))


@mcp.tool()
async def get_promotions(query: str, count: int = 10, country: str = "ie") -> str:
    """Search Tesco groceries and return products with active promotions/deals."""
    result = api_search_products(query, count=count, country=country)
    promoted_products = [product for product in result.products if product.promotions]
    return _json(
        {
            "query": query,
            "country": country.lower(),
            "products": [_promotion_row(product) for product in promoted_products],
        }
    )


@mcp.tool()
async def find_alternatives(product_name: str, count: int = 5, country: str = "ie") -> str:
    """Find similar Tesco products sorted by price, with savings against the first search result."""
    result = api_search_products(product_name, count=count, country=country)
    if not result.products:
        return _json({"product_name": product_name, "country": country.lower(), "baseline": None, "alternatives": []})

    baseline = result.products[0]
    sorted_products = sorted(result.products, key=lambda product: product.price)
    return _json(
        {
            "product_name": product_name,
            "country": country.lower(),
            "baseline": _price_row(baseline),
            "alternatives": [_alternative_row(product, baseline.price) for product in sorted_products],
        }
    )


@mcp.tool()
async def meal_cost_calculator(ingredients: str, country: str = "ie") -> str:
    """Estimate meal cost from comma-separated ingredients using cheapest Tesco matches."""
    parsed_ingredients = _parse_csv_items(ingredients)
    rows = []
    total_cost = 0.0
    nutrition_total = _empty_nutrition_total()

    for ingredient in parsed_ingredients:
        result = api_search_products(ingredient, count=10, country=country)
        cheapest = _cheapest_product(result.products)
        if cheapest is None:
            rows.append({"ingredient": ingredient, "matched_product": None, "price": None, "currency": None})
            continue

        total_cost += cheapest.price
        _add_nutrition(nutrition_total, cheapest.nutrition)
        rows.append(
            {
                "ingredient": ingredient,
                "matched_product": cheapest.title,
                "tpnb": cheapest.tpnb,
                "price": cheapest.price,
                "currency": cheapest.currency,
                "nutrition_per_100g": _nutrition_summary(cheapest),
            }
        )

    return _json(
        {
            "country": country.lower(),
            "ingredients": rows,
            "total_cost": round(total_cost, 2),
            "nutrition_total_per_100g_rough": nutrition_total,
            "note": "Nutrition total sums per-100g values from each matched product; treat as a rough planning estimate.",
        }
    )


@mcp.tool()
async def weekly_shop_estimator(items: str, country: str = "ie") -> str:
    """Estimate weekly shop cost from comma-separated items like 'chicken breast x2, rice x1'."""
    parsed_items = _parse_quantity_items(items)
    rows = []
    total_cost = 0.0

    for item in parsed_items:
        result = api_search_products(item["name"], count=10, country=country)
        cheapest = _cheapest_product(result.products)
        if cheapest is None:
            rows.append({**item, "matched_product": None, "unit_price": None, "line_total": None, "currency": None})
            continue

        line_total = cheapest.price * item["quantity"]
        total_cost += line_total
        rows.append(
            {
                "item": item["name"],
                "quantity": item["quantity"],
                "matched_product": cheapest.title,
                "tpnb": cheapest.tpnb,
                "unit_price": cheapest.price,
                "line_total": round(line_total, 2),
                "currency": cheapest.currency,
            }
        )

    return _json(
        {
            "country": country.lower(),
            "items": rows,
            "total_cost": round(total_cost, 2),
            "per_day_average": round(total_cost / 7, 2),
        }
    )


@mcp.tool()
async def get_nutrition(tpnb: int, country: str = "ie") -> str:
    """Get the per-100g nutrition breakdown for a Tesco product by TPNB ID."""
    product = _require_product(tpnb, country=country)
    return _json(
        {
            "tpnb": product.tpnb,
            "title": product.title,
            "country": country.lower(),
            "nutrition_per_100g": product.nutrition.model_dump(mode="json"),
        }
    )


@mcp.tool()
async def compare_products(
    query: str,
    count: int = 10,
    sort_by: SortBy = "price",
    country: str = "ie",
) -> str:
    """Compare Tesco products side-by-side on price and nutrition.

    sort_by supports: price, protein, calories, protein_per_euro.
    """
    result = api_search_products(query, count=count, country=country)
    products = result.products

    def sort_key(product: Any) -> float:
        if sort_by == "price":
            return product.price
        if sort_by == "protein":
            return -(product.nutrition.protein_g or 0)
        if sort_by == "calories":
            return product.nutrition.calories_kcal if product.nutrition.calories_kcal is not None else float("inf")
        if sort_by == "protein_per_euro":
            return -(product.protein_per_currency or 0)
        return product.price

    sorted_products = sorted(products, key=sort_key)
    return _json(
        {
            "query": query,
            "country": country.lower(),
            "sort_by": sort_by,
            "products": [_comparison_row(product) for product in sorted_products],
        }
    )


@mcp.tool()
async def find_best_value_protein(query: str, count: int = 10, country: str = "ie") -> str:
    """Find Tesco products with the highest protein grams per euro/pound."""
    result = api_search_products(query, count=count, country=country)
    products = sorted(
        result.products,
        key=lambda product: product.protein_per_currency or 0,
        reverse=True,
    )
    return _json(
        {
            "query": query,
            "country": country.lower(),
            "metric": "protein_g_per_unit_currency",
            "products": [_comparison_row(product) for product in products],
        }
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _parse_csv_items(raw: str) -> list[str]:
    """Split comma-separated ingredient list, stripping whitespace."""
    return [item.strip() for item in raw.split(",") if item.strip()]


def _parse_quantity_items(raw: str) -> list[dict[str, Any]]:
    """Parse 'item x2, item x1' format into [{name, quantity}]."""
    items = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        m = _QUANTITY_RE.match(part)
        if m:
            items.append({"name": m.group("name").strip(), "quantity": float(m.group("quantity"))})
        else:
            items.append({"name": part, "quantity": 1.0})
    return items


def _cheapest_product(products: list[Any]) -> Any | None:
    """Return cheapest product from a list, or None."""
    priced = [p for p in products if p.price and p.price > 0]
    return min(priced, key=lambda p: p.price) if priced else None


def _nutrition_summary(product: Any) -> dict[str, float | None]:
    n = product.nutrition
    return {
        "calories_kcal": n.calories_kcal,
        "protein_g": n.protein_g,
        "carbs_g": n.carbs_g,
        "fat_g": n.fat_g,
    }


def _empty_nutrition_total() -> dict[str, float]:
    return {"calories_kcal": 0.0, "protein_g": 0.0, "carbs_g": 0.0, "fat_g": 0.0}


def _add_nutrition(total: dict[str, float], nutrition: Any) -> None:
    for key in total:
        val = getattr(nutrition, key, None)
        if val is not None:
            total[key] += val
    # Round
    for key in total:
        total[key] = round(total[key], 1)


def _promotion_row(product: Any) -> dict[str, Any]:
    return {
        "tpnb": product.tpnb,
        "title": product.title,
        "price": product.price,
        "currency": product.currency,
        "promotions": product.promotions,
        "nutrition_per_100g": _nutrition_summary(product),
    }


def _price_row(product: Any) -> dict[str, Any]:
    return {
        "tpnb": product.tpnb,
        "title": product.title,
        "price": product.price,
        "currency": product.currency,
        "pack_size": product.pack_size,
    }


def _alternative_row(product: Any, baseline_price: float) -> dict[str, Any]:
    savings = round(baseline_price - product.price, 2)
    return {
        "tpnb": product.tpnb,
        "title": product.title,
        "price": product.price,
        "currency": product.currency,
        "pack_size": product.pack_size,
        "savings_vs_baseline": savings,
        "nutrition_per_100g": _nutrition_summary(product),
    }


def _comparison_row(product: Any) -> dict[str, Any]:
    nutrition = product.nutrition
    return {
        "tpnb": product.tpnb,
        "title": product.title,
        "price": product.price,
        "currency": product.currency,
        "pack_size": product.pack_size,
        "unit_price": product.unit_price,
        "unit_of_measure": product.unit_of_measure,
        "protein_per_currency": product.protein_per_currency,
        "nutrition_per_100g": {
            "calories_kcal": nutrition.calories_kcal,
            "protein_g": nutrition.protein_g,
            "carbs_g": nutrition.carbs_g,
            "fat_g": nutrition.fat_g,
            "fibre_g": nutrition.fibre_g,
            "sugar_g": nutrition.sugar_g,
            "salt_g": nutrition.salt_g,
        },
        "promotions": product.promotions,
    }


def main() -> None:
    """Run the Tesco MCP server over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
