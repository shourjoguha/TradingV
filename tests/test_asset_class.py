from app.tickers.asset_class import infer_asset_class


def test_crypto_dash_suffix():
    assert infer_asset_class("BTC-USD") == "crypto"
    assert infer_asset_class("eth-usd") == "crypto"


def test_crypto_concat_suffix():
    assert infer_asset_class("BTCUSDT") == "crypto"
    assert infer_asset_class("ETHUSDC") == "crypto"


def test_etf_known():
    assert infer_asset_class("SPY") == "etf"
    assert infer_asset_class("qqq") == "etf"


def test_stock_default():
    assert infer_asset_class("AAPL") == "stock"
    assert infer_asset_class("TSLA") == "stock"


def test_empty():
    assert infer_asset_class("") == "stock"
