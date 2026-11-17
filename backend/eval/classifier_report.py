"""Report the repeat-buyer classifier against the majority baseline on the same chronological holdout.

Usage (from backend/):  python -m eval.classifier_report [path/to/orders.csv]

The selection is exactly what /api/compare-models does. The extra "diagnostic"
rows score every candidate on the test cutoff for reporting only. They are
not used to choose a model.
"""
import json
import sys
from pathlib import Path

import pandas as pd
from sklearn.metrics import f1_score

from app.comparison import build_examples, compare

BACKEND = Path(__file__).parents[1]


def main(path: Path):
    rows = pd.read_csv(path).to_dict("records")
    result = compare(rows)
    if result["status"] != "ok":
        print(json.dumps(result, indent=2))
        return
    df = pd.DataFrame(rows)
    df["order_date"] = pd.to_datetime(df["order_date"])
    months = pd.period_range(df.order_date.min().to_period("M"), df.order_date.max().to_period("M"), freq="M")
    frame = build_examples(df, months[:-2])
    test = frame[frame.cutoff == result["test_cutoff"]]
    train_val = frame[frame.cutoff < result["test_cutoff"]]
    cols = ["recency", "frequency", "monetary"]
    from app.comparison import DummyClassifier, LogisticRegression, RandomForestClassifier, StandardScaler, make_pipeline
    candidates = {
        "Baseline": DummyClassifier(strategy="most_frequent"),
        "Logistic regression": make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000, class_weight="balanced")),
        "Random forest": RandomForestClassifier(n_estimators=100, max_depth=6, min_samples_leaf=3, class_weight="balanced", random_state=42),
    }
    diagnostic = {name: round(float(f1_score(test.label, m.fit(train_val[cols], train_val.label).predict(test[cols]), zero_division=0)), 4) for name, m in candidates.items()}
    positive_rate = float(test.label.mean())
    report = {
        "data": str(path.name),
        "selected_by_validation_f1": result["selected"],
        "validation_cutoff": result["validation_cutoff"],
        "test_cutoff": result["test_cutoff"],
        "examples": {"train": result["train_examples"], "validation": result["validation_examples"], "test": result["test_examples"]},
        "test_positive_rate": round(positive_rate, 4),
        "test_f1_selected": result["test"]["f1"],
        "test_f1_majority_baseline": result["test_baseline"]["f1"],
        "all_positive_f1_reference": round(2 * positive_rate / (1 + positive_rate), 4),
        "diagnostic_test_f1_all_candidates": diagnostic,
        "validation": {m["name"]: m["validation"] for m in result["models"]},
    }
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else BACKEND / "sample_sales.csv")
