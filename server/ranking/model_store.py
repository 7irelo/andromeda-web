"""
Where trained rankers live and how serving picks them up.

A model is two objects in the default storage, under the private prefix
(never anonymously readable): ``private/models/ranker-<ts>.txt`` (LightGBM's
text format, no pickles) and ``ranker-<ts>.json`` (features, metrics,
calibration, data window, training distribution). The metadata is written
last, so its appearance means the model next to it is complete.

Each process keeps the newest model in memory and looks for a newer metadata
file at most every ``RANKING_MODEL_CHECK_SECONDS``.
"""
import json
import logging
import threading
import time
from dataclasses import dataclass

import numpy as np
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from . import features

logger = logging.getLogger(__name__)

MODEL_DIR = 'private/models/'
PREFIX = 'ranker-'


@dataclass
class LoadedModel:
    name: str
    booster: object
    meta: dict

    @property
    def version(self):
        return self.name

    def predict(self, X):
        """Calibrated P(engage) and per-feature contributions (log-odds, last column is the bias)."""
        raw = self.booster.predict(X, num_threads=1)
        contrib = self.booster.predict(X, pred_contrib=True, num_threads=1)
        return calibrate(raw, self.meta.get('calibration')), contrib


def link(score, kind):
    """The input scale for Platt scaling: log-odds of a probability, or log of v1's positive score."""
    eps = 1e-6
    score = np.asarray(score, dtype=float)
    if kind == 'log':
        return np.log(np.maximum(score, eps))
    p = np.clip(score, eps, 1 - eps)
    return np.log(p / (1 - p))


def calibrate(p, calibration):
    p = np.asarray(p, dtype=float)
    if not calibration:
        return p
    if calibration['method'] == 'isotonic':
        return np.interp(p, calibration['x'], calibration['y'])
    if calibration['method'] == 'platt':
        z = calibration['a'] * link(p, calibration.get('link', 'logit')) + calibration['b']
        return 1.0 / (1.0 + np.exp(-z))
    return p


def save(model_text, meta, stamp):
    """Store a model and its metadata. Returns the metadata's storage name."""
    base = f'{MODEL_DIR}{PREFIX}{stamp}'
    model_name = default_storage.save(f'{base}.txt', ContentFile(model_text.encode()))
    meta = {**meta, 'model_file': model_name}
    return default_storage.save(f'{base}.json', ContentFile(json.dumps(meta, indent=2).encode()))


def latest_metadata_name():
    try:
        _, files = default_storage.listdir(MODEL_DIR)
    except (FileNotFoundError, OSError):
        return None
    names = sorted(f for f in files if f.startswith(PREFIX) and f.endswith('.json'))
    return f'{MODEL_DIR}{names[-1]}' if names else None


def read_metadata(name):
    with default_storage.open(name) as fh:
        return json.loads(fh.read())


def _load(name):
    import lightgbm as lgb

    meta = read_metadata(name)
    if meta.get('feature_version') != features.FEATURE_VERSION or meta.get('features') != features.FEATURES:
        logger.error('Ranker %s was trained on different features; ignoring it', name)
        return None
    with default_storage.open(meta['model_file']) as fh:
        text = fh.read()
    booster = lgb.Booster(model_str=text.decode() if isinstance(text, bytes) else text)
    return LoadedModel(name=name.rsplit('/', 1)[-1].removesuffix('.json'), booster=booster, meta=meta)


_lock = threading.Lock()
_state = {'name': None, 'model': None, 'checked': 0.0}


def current():
    """The newest usable model, or None. Never raises."""
    interval = getattr(settings, 'RANKING_MODEL_CHECK_SECONDS', 60)
    now = time.monotonic()
    if _state['checked'] and now - _state['checked'] < interval:
        return _state['model']
    with _lock:
        if _state['checked'] and now - _state['checked'] < interval:
            return _state['model']
        try:
            name = latest_metadata_name()
            if name and name != _state['name']:
                model = _load(name)
                if model is not None:
                    _state['model'] = model
                    _state['name'] = name
                    logger.info('Loaded feed ranker %s', model.name)
        except Exception:
            logger.exception('Could not load the feed ranker; keeping %s', _state['name'])
        _state['checked'] = now
        return _state['model']


def reset():
    """Forget the cached model (tests, or after deleting models)."""
    with _lock:
        _state.update(name=None, model=None, checked=0.0)
