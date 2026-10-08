from collections import defaultdict
from datetime import date, timedelta

import pandas as pd
from sklearn.dummy import DummyClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, precision_score, recall_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


def evaluate_repeat_purchase(rows):
    if not rows:
        return {"status": "needs_data", "message": "Upload a CSV first"}
    df = pd.DataFrame(rows)
    df["order_date"] = pd.to_datetime(df["order_date"])
    months = pd.period_range(df.order_date.min().to_period("M"), df.order_date.max().to_period("M"), freq="M")
    if len(months) < 4:
        return {"status": "needs_data", "message": "Need orders spanning at least four calendar months"}
    examples = []
    # A cutoff at month end uses only historical orders; the following month supplies labels.
    for month in months[:-1]:
        cutoff = month.to_timestamp(how="end").normalize()
        history = df[df.order_date <= cutoff]
        future = df[(df.order_date > cutoff) & (df.order_date < (month + 2).to_timestamp())]
        returning = set(future.customer_id)
        for cid, group in history.groupby("customer_id"):
            examples.append({"cutoff": str(month), "recency": (cutoff - group.order_date.max()).days, "frequency": len(group), "monetary": group.amount.sum(), "label": int(cid in returning)})
    frame = pd.DataFrame(examples)
    holdout = str(months[-2])
    train, test = frame[frame.cutoff < holdout], frame[frame.cutoff == holdout]
    if len(train) < 10 or len(test) < 3 or train.label.nunique() < 2:
        return {"status": "needs_data", "message": "Need more customer history and both label classes before evaluation"}
    columns = ["recency", "frequency", "monetary"]
    baseline = DummyClassifier(strategy="most_frequent").fit(train[columns], train.label)
    model = make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000, class_weight="balanced"))
    model.fit(train[columns], train.label)

    def metrics(estimator):
        prediction = estimator.predict(test[columns])
        return {"accuracy": round(accuracy_score(test.label, prediction), 3), "precision": round(precision_score(test.label, prediction, zero_division=0), 3), "recall": round(recall_score(test.label, prediction, zero_division=0), 3)}

    return {"status": "ok", "target": "Purchase in following calendar month", "holdout_cutoff": holdout, "train_examples": len(train), "test_examples": len(test), "positive_rate": round(float(test.label.mean()), 3), "baseline": metrics(baseline), "logistic_regression": metrics(model), "note": "Synthetic demo data; metrics do not establish real-world performance"}
