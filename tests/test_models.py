from tesco_mcp.models import TescoNutrition, TescoProduct, TescoSearchResult


def test_tesco_product_defaults() -> None:
    product = TescoProduct(tpnb=12345, title="Test", price=1.99)
    assert product.currency == "EUR"
    assert product.price_eur == 1.99
    assert product.nutrition == TescoNutrition()
    assert product.promotions == []
    assert product.pack_size == ""


def test_uk_product_has_no_price_eur_but_has_local_value_metric() -> None:
    product = TescoProduct(
        tpnb=12345,
        title="Protein yoghurt",
        price=2.00,
        currency="GBP",
        nutrition=TescoNutrition(protein_g=20.0),
    )
    assert product.price_eur is None
    assert product.protein_per_currency == 10.0


def test_tesco_search_result_defaults() -> None:
    result = TescoSearchResult(query="oats")
    assert result.country == "ie"
    assert result.total == 0
    assert result.products == []
