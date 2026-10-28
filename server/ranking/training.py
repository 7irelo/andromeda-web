"""
Training and offline evaluation for ranker v2.

* Labels: did the viewer engage (like, comment, save, share, open) within
  24 hours of the impression. Impressions younger than that are left out,
  because their label isn't final yet.
* Split by time, never at random: the oldest 70% of impressions train, the
  next 15% pick the number of trees (early stopping) and fit the calibration,
  and the newest 15% are the test set. A random split would let the model
  learn from the future it's evaluated on (the same post, trending, in both).
* Baseline: ranking v1's heuristic score on the same test impressions, put
  through the same kind of calibration so log-loss and ECE are comparable.
"""
import math
from datetime import timedelta

import numpy as np
from django.utils import timezone

from . import features
from .model_store import calibrate, link as link_fn
from .models import FeedImpression

LABEL_DELAY = timedelta(hours=24)
SPLIT = (0.70, 0.15, 0.15)
BINS = 10
PARAMS = {
    'objective': 'binary',
    'learning_rate': 0.05,
    'num_leaves': 15,
    'min_data_in_leaf': 20,
    'feature_fraction': 0.9,
    'bagging_fraction': 0.8,
    'bagging_freq': 1,
    'lambda_l2': 1.0,
    'max_cat_to_onehot': 8,
    'deterministic': True,
    'force_col_wise': True,
    'num_threads': 2,
    'seed': 7,
    'verbose': -1,
}
MAX_ROUNDS = 500
EARLY_STOPPING = 30


class NotEnoughData(Exception):
    pass


def load_dataset(since, until=None, synthetic=False):
    """Matured impressions with logged features in ``[since, until)``, oldest first."""
    until = min(until or timezone.now(), timezone.now() - LABEL_DELAY)
    rows = (FeedImpression.objects
            .filter(served_at__gte=since, served_at__lt=until, synthetic=synthetic, features__isnull=False)
            .order_by('served_at', 'id').values_list('features', 'engaged', 'served_at'))
    X, y, t = [], [], []
    width = len(features.FEATURES)
    for vec, engaged, served_at in rows.iterator(chunk_size=5000):
        if isinstance(vec, list) and len(vec) == width:
            X.append(vec)
            y.append(1 if engaged else 0)
            t.append(served_at)
    return np.asarray(X, dtype=float).reshape(-1, width), np.asarray(y, dtype=int), t


def time_split(t, fractions=SPLIT):
    """
    Index ranges (train, validation, test) over rows sorted by time. Cuts move
    forward past ties, so no timestamp is on both sides of a boundary.
    """
    n = len(t)
    cuts = []
    for frac in (fractions[0], fractions[0] + fractions[1]):
        i = int(n * frac)
        while 0 < i < n and t[i] == t[i - 1]:
            i += 1
        cuts.append(i)
    a, b = cuts
    return slice(0, a), slice(a, b), slice(b, n)


# ── Metrics ──────────────────────────────────────────────────────────────────

def reliability(y, p, bins=BINS):
    """Rows of (bin_lo, bin_hi, count, mean predicted, observed rate) over equal-width bins."""
    y, p = np.asarray(y), np.asarray(p)
    out = []
    for i in range(bins):
        lo, hi = i / bins, (i + 1) / bins
        mask = (p >= lo) & ((p < hi) if i < bins - 1 else (p <= hi))
        n = int(mask.sum())
        out.append({'lo': lo, 'hi': hi, 'n': n,
                    'predicted': float(p[mask].mean()) if n else None,
                    'observed': float(y[mask].mean()) if n else None})
    return out


def ece(y, p, bins=BINS):
    """Expected calibration error: |predicted - observed| per bin, weighted by the bin's share."""
    total = len(y)
    if not total:
        return float('nan')
    return float(sum(r['n'] / total * abs(r['predicted'] - r['observed'])
                     for r in reliability(y, p, bins) if r['n']))


def evaluate(y, p, ranking_score=None):
    """
    AUC, log-loss and calibration of probabilities ``p``. AUC is taken on
    ``ranking_score`` when given (the uncalibrated score: calibration steps add
    ties that would understate how well it orders posts).
    """
    from sklearn.metrics import log_loss, roc_auc_score

    p = np.clip(np.asarray(p, dtype=float), 1e-6, 1 - 1e-6)
    both = len(set(np.asarray(y).tolist())) == 2
    return {
        'n': int(len(y)),
        'positives': int(np.sum(y)),
        'auc': float(roc_auc_score(y, p if ranking_score is None else ranking_score)) if both else None,
        'log_loss': float(log_loss(y, p, labels=[0, 1])),
        'ece': ece(y, p),
        'reliability': reliability(y, p),
    }


ISOTONIC_MIN_POSITIVES = 500


def fit_calibration(score, y, link='logit'):
    """
    Map scores to probabilities, fitted on the validation split and stored as
    JSON. Isotonic when there are enough positives to pin down its steps;
    otherwise Platt scaling (a logistic fit on ``link(score)``), since
    isotonic on a few hundred positives overfits the sparse top bins.
    ``link`` is 'logit' for the model's probabilities, 'log' for v1's scores.
    """
    from sklearn.isotonic import IsotonicRegression
    from sklearn.linear_model import LogisticRegression

    y = np.asarray(y)
    if len(set(y.tolist())) < 2:
        return None
    score = np.asarray(score, dtype=float)
    if y.sum() >= ISOTONIC_MIN_POSITIVES:
        iso = IsotonicRegression(out_of_bounds='clip', y_min=0.0, y_max=1.0).fit(score, y)
        return {'method': 'isotonic', 'x': iso.X_thresholds_.tolist(), 'y': iso.y_thresholds_.tolist()}
    lr = LogisticRegression(C=1e6, max_iter=1000).fit(link_fn(score, link).reshape(-1, 1), y)
    return {'method': 'platt', 'link': link, 'a': float(lr.coef_[0][0]), 'b': float(lr.intercept_[0])}


# ── Drift reference ──────────────────────────────────────────────────────────

def distribution(x, edges):
    """Share of values in each bin defined by ``edges`` (len(edges) + 1 bins)."""
    x = np.asarray(x, dtype=float)
    counts = np.bincount(np.searchsorted(edges, x, side='right'), minlength=len(edges) + 1)
    return (counts / max(len(x), 1)).tolist()


def reference_distributions(X):
    """Per-feature decile edges and bin shares on the training split, for drift (PSI) checks."""
    out = {}
    for i, name in enumerate(features.FEATURES):
        col = X[:, i]
        edges = np.unique(np.quantile(col, np.linspace(0.1, 0.9, 9))).tolist() if len(col) else []
        out[name] = {'edges': edges, 'expected': distribution(col, edges), 'mean': float(col.mean()) if len(col) else 0.0}
    return out


def psi(expected, actual, eps=1e-4):
    """Population Stability Index between two bin-share vectors. > 0.2 is usually read as real drift."""
    total = 0.0
    for e, a in zip(expected, actual, strict=True):
        e, a = max(e, eps), max(a, eps)
        total += (a - e) * math.log(a / e)
    return total


# ── Training ─────────────────────────────────────────────────────────────────

def train(X, y, t, params=None, min_rows=200):
    """
    Train, calibrate and evaluate. Returns ``(booster, report)``; the report
    holds everything the metadata file records.
    """
    import lightgbm as lgb

    if len(y) < min_rows:
        raise NotEnoughData(f'Need at least {min_rows} matured impressions, found {len(y)}.')
    tr, va, te = time_split(t)
    for name, part in (('train', tr), ('validation', va), ('test', te)):
        if len(set(y[part].tolist())) < 2:
            raise NotEnoughData(f'The {name} split needs both engaged and ignored impressions.')

    cat = [features.INDEX[c] for c in features.CATEGORICAL]
    dtrain = lgb.Dataset(X[tr], y[tr], feature_name=features.FEATURES, categorical_feature=cat, free_raw_data=False)
    dval = lgb.Dataset(X[va], y[va], reference=dtrain, categorical_feature=cat)
    booster = lgb.train({**PARAMS, **(params or {})}, dtrain, num_boost_round=MAX_ROUNDS, valid_sets=[dval],
                        valid_names=['validation'],
                        callbacks=[lgb.early_stopping(EARLY_STOPPING, verbose=False)])

    raw_val = booster.predict(X[va], num_iteration=booster.best_iteration)
    calibration = fit_calibration(raw_val, y[va])
    raw_test = booster.predict(X[te], num_iteration=booster.best_iteration)
    model = evaluate(y[te], calibrate(raw_test, calibration), ranking_score=raw_test)

    base_val, base_test = features.heuristic_score(X[va]), features.heuristic_score(X[te])
    base_calibration = fit_calibration(base_val, y[va], link='log')
    baseline = evaluate(y[te], calibrate(base_test, base_calibration), ranking_score=base_test)
    importance = dict(zip(features.FEATURES, booster.feature_importance('gain').tolist(), strict=True))

    report = {
        'rows': {'train': int(tr.stop - tr.start), 'validation': int(va.stop - va.start),
                 'test': int(te.stop - te.start)},
        'data_window': {
            'train': [t[tr.start].isoformat(), t[tr.stop - 1].isoformat()],
            'validation': [t[va.start].isoformat(), t[va.stop - 1].isoformat()],
            'test': [t[te.start].isoformat(), t[te.stop - 1].isoformat()],
        },
        'best_iteration': int(booster.best_iteration or booster.current_iteration()),
        'calibration': calibration,
        'metrics': {'model': model, 'baseline_v1': baseline},
        'feature_importance_gain': importance,
        'training_distribution': reference_distributions(X[tr]),
        'params': {**PARAMS, **(params or {})},
    }
    return booster, report
