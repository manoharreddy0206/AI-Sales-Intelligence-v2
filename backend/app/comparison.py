import pandas as pd
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score


def compare(rows):
    if not rows:
        return {'status': 'needs_data', 'message': 'Upload multi-month data first.'}
    df = pd.DataFrame(rows)
    df.order_date = pd.to_datetime(df.order_date)
    months = pd.period_range(df.order_date.min().to_period('M'), df.order_date.max().to_period('M'), freq='M')
    if len(months) < 6:
        return {'status': 'needs_data', 'message': 'Need at least six months. The newest month is excluded because it may be incomplete.'}
    examples = []
    for month in months[:-2]:
        cutoff = month.to_timestamp(how='end').normalize()
        history = df[df.order_date <= cutoff]
        returning = set(df[(df.order_date > cutoff) & (df.order_date < (month + 2).to_timestamp())].customer_id)
        for cid, group in history.groupby('customer_id'):
            examples.append({'cutoff': str(month), 'recency': (cutoff-group.order_date.max()).days, 'frequency': len(group), 'monetary': group.amount.sum(), 'label': int(cid in returning)})
    frame = pd.DataFrame(examples)
    cutoffs = sorted(frame.cutoff.unique())
    train = frame[frame.cutoff < cutoffs[-2]]
    validation = frame[frame.cutoff == cutoffs[-2]]
    test = frame[frame.cutoff == cutoffs[-1]]
    if len(train) < 10 or min(len(validation), len(test)) < 3 or any(part.label.nunique() < 2 for part in [train, validation, test]):
        return {'status': 'needs_data', 'message': 'Need more customers and both classes in train, validation and test.'}
    cols = ['recency', 'frequency', 'monetary']
    factories = {
        'Baseline': lambda: DummyClassifier(strategy='most_frequent'),
        'Logistic regression': lambda: make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000, class_weight='balanced')),
        'Random forest': lambda: RandomForestClassifier(n_estimators=100, max_depth=6, min_samples_leaf=3, class_weight='balanced', random_state=42),
    }
    def metrics(model, part):
        pred = model.predict(part[cols])
        return {name: round(float(fn(part.label, pred, **({} if name == 'accuracy' else {'zero_division': 0}))), 4) for name, fn in [('accuracy', accuracy_score), ('precision', precision_score), ('recall', recall_score), ('f1', f1_score)]}
    results = []
    for name, factory in factories.items():
        model = factory().fit(train[cols], train.label)
        results.append({'name': name, 'validation': metrics(model, validation)})
    winner = max(results, key=lambda r: r['validation']['f1'])['name']
    combined = pd.concat([train, validation])
    selected = factories[winner]().fit(combined[cols], combined.label)
    baseline = factories['Baseline']().fit(combined[cols], combined.label)
    return {'status': 'ok', 'selected': winner, 'selection_metric': 'validation F1', 'models': results, 'test': metrics(selected, test), 'test_baseline': metrics(baseline, test), 'validation_cutoff': cutoffs[-2], 'test_cutoff': cutoffs[-1], 'train_examples': len(train), 'validation_examples': len(validation), 'test_examples': len(test), 'note': 'Experiment only; no production model is promoted. Newest month excluded; earlier months are assumed complete.'}
