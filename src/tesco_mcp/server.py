"""FastMCP server exposing Tesco IE/UK grocery shopping tools."""

from __future__ import annotations

import json
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP

from .tesco_api import get_product as api_get_product
from .tesco_api import search_products as api_search_products

mcp = FastMCP("tesco", dependencies=["httpx", "pydantic"])

SortBy = Literal["price", "protein", "calories", "protein_per_euro"]


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
