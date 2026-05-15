"""Pydantic models for Tesco grocery products."""

from __future__ import annotations

from pydantic import BaseModel, Field, computed_field


class TescoNutrition(BaseModel):
    """Per-100g macronutrient values parsed from Tesco's nutrition table."""

    calories_kcal: float | None = None
    protein_g: float | None = None
    carbs_g: float | None = None
    fat_g: float | None = None
    fibre_g: float | None = None
    sugar_g: float | None = None
    salt_g: float | None = None


class TescoProduct(BaseModel):
    """A single Tesco product with price, pack size, promotions, and nutrition."""

    tpnb: int
    tesco_id: str = ""
    gtin: str = ""
    title: str
    image_url: str = ""
    price: float = Field(description="Current shelf price in the local country currency")
    currency: str = Field(default="EUR", description="ISO currency code, e.g. EUR or GBP")
    unit_price: float | None = None
    unit_of_measure: str = ""
    pack_size: str = ""
    promotions: list[str] = Field(default_factory=list)
    nutrition: TescoNutrition = Field(default_factory=TescoNutrition)
    ingredients_html: str = ""

    @computed_field  # type: ignore[prop-decorator]
    @property
    def price_eur(self) -> float | None:
        """Backward-compatible IE price field used by nutrition value tooling."""
        return self.price if self.currency == "EUR" else None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def protein_per_currency(self) -> float | None:
        """Protein grams per unit of local currency, when both values exist."""
        if not self.price or self.nutrition.protein_g is None:
            return None
        return self.nutrition.protein_g / self.price


class TescoSearchResult(BaseModel):
    """Result of a Tesco product search."""

    query: str
    country: str = "ie"
    total: int = 0
    products: list[TescoProduct] = Field(default_factory=list)
