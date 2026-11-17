from pathlib import Path

import pandas as pd

from app.comparison import build_examples, compare

SAMPLE = Path(__file__).parents[1] / "sample_sales.csv"


def frame():
    df = pd.read_csv(SAMPLE)
    df["order_date"] = pd.to_datetime(df["order_date"])
    return df


def test_features_only_use_orders_available_at_the_cutoff():
    df = frame()
    months = pd.period_range("2025-01", "2025-06", freq="M")
    full = build_examples(df, months)
    for month in months:
        cutoff = month.to_timestamp(how="end").normalize()
        truncated = build_examples(df[df.order_date <= cutoff], [month])
        cols = ["customer_id", "recency", "frequency", "monetary"]
        expected = full[full.cutoff == str(month)][cols].reset_index(drop=True)
        pd.testing.assert_frame_equal(truncated[cols].reset_index(drop=True), expected)


def test_comparison_uses_a_later_chronological_test_period():
    result = compare(pd.read_csv(SAMPLE).to_dict("records"))
    assert result["status"] == "ok"
    assert result["validation_cutoff"] < result["test_cutoff"]
    assert {m["name"] for m in result["models"]} == {"Baseline", "Logistic regression", "Random forest"}
    assert result["selected"] in {m["name"] for m in result["models"]}
    assert result["test_examples"] == 60
    assert compare([])["status"] == "needs_data"
