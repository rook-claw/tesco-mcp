"""Tesco grocery API client for product search, pricing, and nutrition data.

Two-step flow:
  1. REST search at search.api.tesco.com -> product IDs (TPNBs)
  2. GraphQL batch at xapi.tesco.com -> full details with price and nutrition

The endpoints and API key are public assets used by Tesco's own web frontend.
No customer authentication or account credentials are required for search.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence

import httpx

from .models import TescoNutrition, TescoProduct, TescoSearchResult

SEARCH_BASE_URL = "https://search.api.tesco.com/search"
GRAPHQL_URL = "https://xapi.tesco.com/"
API_KEY = "TvOSZJHlEk0pjniDGQFAc9Q59WGAR4dA"  # public, embedded in Tesco frontend JS
DEFAULT_COUNTRY = "ie"
DEFAULT_TIMEOUT = 10.0
MAX_SEARCH_RESULTS = 10

_KCAL_RE = re.compile(r"(\d+(?:\.\d+)?)\s*kcal", re.IGNORECASE)
_GRAM_RE = re.compile(r"(\d+(?:\.\d+)?)\s*g", re.IGNORECASE)
_LESS_THAN_RE = re.compile(r"<\s*(\d+(?:\.\d+)?)\s*g", re.IGNORECASE)

_PRODUCT_QUERY = """\
query GetProductByTpnb($tpnb: String) {
  product(tpnb: $tpnb) {
    id
    gtin
    title
    defaultImageUrl
    price {
      actual
      unitPrice
      unitOfMeasure
    }
    details {
      packSize {
        value
        units
      }
      nutrition {
        name
        value1
        value2
        value3
        value4
      }
      ingredients
    }
    promotions {
      description
    }
  }
}"""


@dataclass(frozen=True)
class TescoCountryConfig:
    """Country-specific Tesco API request settings."""

    code: str
    region: str
    language: str
    currency: str
    website_origin: str


COUNTRIES: dict[str, TescoCountryConfig] = {
    "ie": TescoCountryConfig(
        code="ie",
        region="IE",
        language="en-IE",
        currency="EUR",
        website_origin="https://www.tesco.ie",
    ),
    "uk": TescoCountryConfig(
        code="uk",
        region="UK",
        language="en-GB",
        currency="GBP",
        website_origin="https://www.tesco.com",
    ),
}


class TescoApiError(RuntimeError):
    """Raised when Tesco API requests fail or return unsupported data."""


def get_country_config(country: str = DEFAULT_COUNTRY) -> TescoCountryConfig:
    """Return API settings for a supported country code."""
    normalized = country.lower().strip()
    try:
        return COUNTRIES[normalized]
    except KeyError as exc:
        supported = ", ".join(sorted(COUNTRIES))
        raise ValueError(f"Unsupported country '{country}'. Supported countries: {supported}") from exc


def parse_nutrition(raw_rows: list[dict[str, str | None]]) -> TescoNutrition:
    """Extract numeric per-100g macros from Tesco nutrition table rows."""
    result: dict[str, float | None] = {}
    for row in raw_rows:
        name = (row.get("name") or "").strip().lower()
        value = row.get("value1") or ""

        if name == "energy":
            match = _KCAL_RE.search(value)
            if match:
                result["calories_kcal"] = float(match.group(1))
        elif name == "protein":
            result["protein_g"] = _extract_grams(value)
        elif name in {"carbohydrate", "carbohydrates", "available carbohydrate"}:
            result["carbs_g"] = _extract_grams(value)
        elif name == "fat":
            result["fat_g"] = _extract_grams(value)
        elif name == "fibre":
            result["fibre_g"] = _extract_grams(value)
        elif name in {"sugars", "sugar"}:
            result["sugar_g"] = _extract_grams(value)
        elif name == "salt":
            result["salt_g"] = _extract_grams(value)

    return TescoNutrition(**result)


def _extract_grams(value: str) -> float | None:
    """Parse a gram value, including Tesco trace formats like '<0.01g'."""
    match = _LESS_THAN_RE.search(value)
    if match:
        return float(match.group(1))
    match = _GRAM_RE.search(value)
    return float(match.group(1)) if match else None


def _headers(config: TescoCountryConfig, *, include_api_key: bool = True) -> dict[str, str]:
    headers = {
        "region": config.region,
        "language": config.language,
        "content-type": "application/json",
        "accept": "application/json",
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
    }
    if include_api_key:
        headers["x-apikey"] = API_KEY
    return headers


def search_tpnbs(
    query: str,
    *,
    count: int = MAX_SEARCH_RESULTS,
    country: str = DEFAULT_COUNTRY,
    client: httpx.Client | None = None,
) -> tuple[list[int], int]:
    """Search Tesco groceries for product IDs (TPNBs).

    Returns (list_of_tpnbs, total_result_count).
    """
    if not query.strip():
        raise ValueError("query must not be empty")
    if count < 1:
        raise ValueError("count must be at least 1")

    config = get_country_config(country)
    bounded_count = min(count, 50)
    params = {
        "distchannel": "ghs",
        "query": query,
        "count": bounded_count,
        "geo": config.code,
    }
    headers = {"User-Agent": _headers(config)["User-Agent"]}

    if client is not None:
        response = client.get(SEARCH_BASE_URL, params=params, headers=headers)
    else:
        response = httpx.get(SEARCH_BASE_URL, params=params, headers=headers, timeout=DEFAULT_TIMEOUT)
    response.raise_for_status()

    data = response.json()
    products = data.get(config.code, {}).get("ghs", {}).get("products", {})
    results = products.get("results", [])
    total = products.get("totals", {}).get("all", 0)
    tpnbs = [int(item["tpnb"]) for item in results if item.get("tpnb")]
    return tpnbs, int(total or 0)


def hydrate_products(
    tpnbs: Sequence[int],
    *,
    country: str = DEFAULT_COUNTRY,
    client: httpx.Client | None = None,
) -> list[TescoProduct]:
    """Fetch full product details for TPNBs via Tesco's GraphQL endpoint."""
    if not tpnbs:
        return []

    config = get_country_config(country)
    batch = [
        {
            "operationName": "GetProductByTpnb",
            "variables": {"tpnb": str(tpnb)},
            "query": _PRODUCT_QUERY,
        }
        for tpnb in tpnbs
    ]

    if client is not None:
        response = client.post(GRAPHQL_URL, json=batch, headers=_headers(config))
    else:
        response = httpx.post(GRAPHQL_URL, json=batch, headers=_headers(config), timeout=DEFAULT_TIMEOUT)
    response.raise_for_status()

    payload = response.json()
    if not isinstance(payload, list):
        raise TescoApiError("Unexpected Tesco GraphQL response shape")

    products: list[TescoProduct] = []
    for index, result in enumerate(payload):
        product_data = result.get("data", {}).get("product") if isinstance(result, dict) else None
        if product_data is None:
            continue
        products.append(_parse_product(int(tpnbs[index]), product_data, config))
    return products


def get_product(
    tpnb: int,
    *,
    country: str = DEFAULT_COUNTRY,
    client: httpx.Client | None = None,
) -> TescoProduct | None:
    """Get one Tesco product by TPNB."""
    products = hydrate_products([tpnb], country=country, client=client)
    return products[0] if products else None


def search_products(
    query: str,
    *,
    count: int = MAX_SEARCH_RESULTS,
    country: str = DEFAULT_COUNTRY,
    client: httpx.Client | None = None,
) -> TescoSearchResult:
    """Search Tesco and hydrate the returned products with price and nutrition."""
    tpnbs, total = search_tpnbs(query, count=count, country=country, client=client)
    products = hydrate_products(tpnbs, country=country, client=client)
    return TescoSearchResult(query=query, country=country.lower(), total=total, products=products)


def _parse_product(tpnb: int, data: dict, config: TescoCountryConfig) -> TescoProduct:
    """Convert a raw GraphQL product response to a TescoProduct model."""
    price_data = data.get("price") or {}
    details = data.get("details") or {}

    pack_sizes = details.get("packSize") or []
    pack_size = ""
    if pack_sizes:
        first_pack_size = pack_sizes[0]
        pack_size = f"{first_pack_size.get('value', '')}{first_pack_size.get('units', '')}".strip()

    nutrition_rows = details.get("nutrition") or []
    nutrition = parse_nutrition(nutrition_rows)

    ingredients = details.get("ingredients") or []
    ingredients_html = ingredients[0] if ingredients else ""

    promotions = data.get("promotions") or []
    promo_descriptions = [promo["description"] for promo in promotions if promo.get("description")]

    return TescoProduct(
        tpnb=tpnb,
        tesco_id=data.get("id", ""),
        gtin=data.get("gtin", ""),
        title=data.get("title", ""),
        image_url=data.get("defaultImageUrl", ""),
        price=float(price_data.get("actual") or 0),
        currency=config.currency,
        unit_price=price_data.get("unitPrice"),
        unit_of_measure=price_data.get("unitOfMeasure", ""),
        pack_size=pack_size,
        promotions=promo_descriptions,
        nutrition=nutrition,
        ingredients_html=ingredients_html,
    )


__all__ = [
    "COUNTRIES",
    "TescoApiError",
    "TescoCountryConfig",
    "TescoNutrition",
    "TescoProduct",
    "TescoSearchResult",
    "get_country_config",
    "get_product",
    "hydrate_products",
    "parse_nutrition",
    "search_products",
    "search_tpnbs",
]
