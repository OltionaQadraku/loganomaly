"""Experiments for the second LogSense revision.

Run from the repository root, same place as extra_experiments.py:

    python revision_experiments.py                 # all experiments
    python revision_experiments.py leakage         # one experiment by name

Needs the same feature files as extra_experiments.py:
    data/features/X_counts_full.npy       data/features/y_full.npy
    data/features/X_counts_full_bgl.npy   data/features/y_full_bgl.npy

Every printed line is tagged with the slot it fills in the manuscript,
[G1], [H1], ... The slots are highlighted in yellow in the revised .docx.
"""
import sys
import time

import numpy as np
from sklearn.decomposition import PCA
from sklearn.ensemble import IsolationForest
from sklearn.feature_extraction.text import TfidfTransformer
from sklearn.metrics import average_precision_score, f1_score
from sklearn.model_selection import train_test_split
from sklearn.neighbors import LocalOutlierFactor

SEED = 42
LOF_SAMPLE = 50_000
HDFS = ('data/features/X_counts_full.npy', 'data/features/y_full.npy')
BGL = ('data/features/X_counts_full_bgl.npy', 'data/features/y_full_bgl.npy')


def load(paths):
    return np.load(paths[0]), np.load(paths[1])


def pca_errors(model, data):
    return np.mean((data - model.inverse_transform(model.transform(data))) ** 2, axis=1)


def lof_subsample(X_normal, seed=SEED):
    if len(X_normal) <= LOF_SAMPLE:
        return X_normal
    rng = np.random.default_rng(seed)
    return X_normal[rng.choice(len(X_normal), LOF_SAMPLE, replace=False)]


def score_models(X_tr_normal, X_te, y_te, r, models=('PCA', 'LOF')):
    """PR AUC and realistic-threshold F1 for each model.

    Realistic threshold = (100 - r)-th percentile of normal TRAINING scores
    for PCA, and contamination=r for LOF and IF, as in the paper.
    """
    out = {}
    if 'PCA' in models:
        pca = PCA(n_components=5, random_state=SEED).fit(X_tr_normal)
        thr = np.percentile(pca_errors(pca, X_tr_normal), 100 * (1 - r))
        err = pca_errors(pca, X_te)
        out['PCA'] = (average_precision_score(y_te, err), f1_score(y_te, err > thr))
    if 'LOF' in models:
        lof = LocalOutlierFactor(n_neighbors=20, contamination=r, novelty=True)
        lof.fit(lof_subsample(X_tr_normal))
        s = -lof.score_samples(X_te)
        out['LOF'] = (average_precision_score(y_te, s), f1_score(y_te, lof.predict(X_te) == -1))
    for name, ms in (('IF', 256), ('IF-all', 1.0)):
        if name in models:
            ms = min(ms, len(X_tr_normal)) if isinstance(ms, int) else ms
            inf = IsolationForest(n_estimators=100, max_samples=ms, contamination=r,
                                  random_state=SEED).fit(X_tr_normal)
            s = -inf.score_samples(X_te)
            out[name] = (average_precision_score(y_te, s), f1_score(y_te, inf.predict(X_te) == -1))
    return out


# ---------------------------------------------------------------------------
# G. Leakage check: vocabulary and IDF from training units only
# ---------------------------------------------------------------------------
def leakage():
    """Templates and the count matrix were built from the whole file.

    A parser fitted on training lines only cannot know templates that first
    appear in the test part. We simulate that by merging every template with
    zero count in all TRAINING units (normal and anomalous) into a single
    'unseen event' column. TF-IDF weights are refitted on training units only.
    Small differences to the paper numbers mean the leakage is negligible.
    """
    print('\n=== [G] Train-only vocabulary and IDF (random split, seed 42) ===')
    for name, paths in (('HDFS', HDFS), ('BGL', BGL)):
        X, y = load(paths)
        X_tr, X_te, y_tr, y_te = train_test_split(
            X, y, test_size=0.3, stratify=y, random_state=SEED)
        r = float(y.mean())
        seen = X_tr.sum(axis=0) > 0
        print(f'\n-- {name}: {int((~seen).sum())} of {X.shape[1]} templates never occur '
              f'in training units, {int((X_te[:, ~seen].sum(axis=1) > 0).sum())} '
              f'test units contain one --')

        def merge(M):
            return np.hstack([M[:, seen], M[:, ~seen].sum(axis=1, keepdims=True)])

        before = score_models(X_tr[y_tr == 0], X_te, y_te, r)
        after = score_models(merge(X_tr)[y_tr == 0], merge(X_te), y_te, r)
        for m in before:
            (ap0, f0), (ap1, f1) = before[m], after[m]
            print(f'  [G1] {name} {m:<4} counts  PR AUC {ap0:.3f} -> {ap1:.3f} '
                  f'(diff {ap1 - ap0:+.3f})   F1 {f0:.3f} -> {f1:.3f}')

        if name == 'HDFS':
            tf_all = TfidfTransformer().fit(X)  # what the paper did
            tf_tr = TfidfTransformer().fit(X_tr)  # train-only IDF
            models = ('PCA', 'LOF', 'IF')
            b = score_models(tf_all.transform(X_tr[y_tr == 0]).toarray(),
                             tf_all.transform(X_te).toarray(), y_te, r, models)
            a = score_models(tf_tr.transform(X_tr[y_tr == 0]).toarray(),
                             tf_tr.transform(X_te).toarray(), y_te, r, models)
            for m in models:
                print(f'  [G2] HDFS {m:<4} TF-IDF  PR AUC {b[m][0]:.3f} -> {a[m][0]:.3f} '
                      f'(diff {a[m][0] - b[m][0]:+.3f})')


# ---------------------------------------------------------------------------
# H. Chronological split for every detector, not only PCA
# ---------------------------------------------------------------------------
def chronological_all():
    """First 70% of units in file order train, last 30% test."""
    print('\n=== [H] Chronological split, all detectors ===')
    for name, paths in (('HDFS', HDFS), ('BGL', BGL)):
        X, y = load(paths)
        cut = int(0.7 * len(X))
        X_tr, y_tr, X_te, y_te = X[:cut], y[:cut], X[cut:], y[cut:]
        r = float(y_tr.mean())
        res = score_models(X_tr[y_tr == 0], X_te, y_te, r,
                           models=('PCA', 'LOF', 'IF', 'IF-all'))
        print(f'\n-- {name} (test anomaly rate {y_te.mean():.3f} = random PR AUC) --')
        for m, (ap, f) in res.items():
            print(f'  [H1] {name} {m:<6} PR AUC={ap:.3f}  F1={f:.3f}')


# ---------------------------------------------------------------------------
# J. More PCA components under the chronological split (BGL)
# ---------------------------------------------------------------------------
def components_chronological():
    """Random split: 200 components give PR AUC 0.993 on BGL.

    If that holds chronologically, more components genuinely help. If it
    collapses, the random-split gain came from near-duplicate windows of the
    same period landing in both train and test.
    """
    print('\n=== [J] BGL PCA components, chronological split ===')
    X, y = load(BGL)
    cut = int(0.7 * len(X))
    X_tr, y_tr, X_te, y_te = X[:cut], y[:cut], X[cut:], y[cut:]
    X_n = X_tr[y_tr == 0]
    r = float(y_tr.mean())
    for k in (5, 20, 50, 100, 200):
        pca = PCA(n_components=k, random_state=SEED).fit(X_n)
        thr = np.percentile(pca_errors(pca, X_n), 100 * (1 - r))
        err = pca_errors(pca, X_te)
        print(f'  [J1] k={k:<4} var={pca.explained_variance_ratio_.sum() * 100:6.2f}%  '
              f'PR AUC={average_precision_score(y_te, err):.3f}  F1={f1_score(y_te, err > thr):.3f}')


EXPERIMENTS = {
    'leakage': leakage,
    'chronological_all': chronological_all,
    'components_chronological': components_chronological,
}

if __name__ == '__main__':
    chosen = sys.argv[1:] or list(EXPERIMENTS)
    for key in chosen:
        if key not in EXPERIMENTS:
            print(f'unknown experiment: {key}\navailable: {", ".join(EXPERIMENTS)}')
            raise SystemExit(1)
    start = time.time()
    for key in chosen:
        EXPERIMENTS[key]()
    print(f'\ndone in {time.time() - start:.1f}s')
