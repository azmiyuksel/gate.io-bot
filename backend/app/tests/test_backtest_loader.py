from app.backtest.engine import HistoricalDataLoader


def test_loader_deduplicates_and_detects_missing_candles() -> None:
    csv_data = """timestamp,open,high,low,close,volume
2024-01-01T00:00:00Z,100,101,99,100,1
2024-01-01T00:00:00Z,100,101,99,100,1
2024-01-01T02:00:00Z,102,103,101,102,1
"""
    frame = HistoricalDataLoader(db=None).load_from_csv(csv_data, "1h")
    assert len(frame) == 2
    assert len(frame.attrs["missing_candles"]) == 1
