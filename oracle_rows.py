"""The missing Table 2 rows: LOF (oracle), IF (oracle), and two diagnostic rows.

Step B2 of the change plan. The oracle threshold flags the top r% of TEST units
by score, where r is the exact test anomaly rate, then scores P/R/F1 against the
labels. PR AUC is threshold-free, so it is identical to the realistic row.

Run from the repository root, same place as paper_numbers.py:

    python oracle_rows.py

Needs the feature files created by notebooks 03-06 (HDFS) and 12 (BGL):
    data/features/X_counts_full.npy       data/features/y_full.npy
    data/features/X_counts_full_bgl.npy   data/features/y_full_bgl.npy

Prints rows ready to paste into Table 2, tab-separated.
"""
import sys

import numpy as np
from sklearn.decomposition import PCA
from sklearn.ensemble import IsolationForest
from sklearn.metrics import average_precision_score, f1_score, precision_score, recall_score
from sklearn.model_selection import train_test_split
from sklearn.neighbors import LocalOutlierFactor

SEED = 42
LOF_FIT_CAP = 50_000  # same cap the paper uses, keeps LOF affordable
DATASETS = {
    'HDFS': ('data/features/X_counts_full.npy', 'data/features/y_full.npy'),
    'BGL': ('data/features/X_counts_full_bgl.npy', 'data/features/y_full_bgl.npy'),
}


def oracle_predict(scores, r):
    """Flag the top r% of test units by score. Higher score = more anomalous.

    Uses >= because duplicate count vectors give many tied scores at the cut
    (1,570 HDFS sessions for LOF); with > they would all be left unflagged.
    """
    cut = np.percentile(scores, 100 * (1 - r))
    return (scores >= cut).astype(int)


def row(name, y_true, scores, r):
    pred = oracle_predict(scores, r)
    return (name,
            precision_score(y_true, pred, zero_division=0),
            recall_score(y_true, pred, zero_division=0),
            f1_score(y_true, pred, zero_division=0),
            average_precision_score(y_true, scores))


def scores_for(dataset):
    X = np.load(DATASETS[dataset][0])
    y = np.load(DATASETS[dataset][1])
    r = float(y.mean())
    X_tr, X_te, y_tr, y_te = train_test_split(
        X, y, test_size=0.3, stratify=y, random_state=SEED)
    X_normal = X_tr[y_tr == 0]

    rng = np.random.default_rng(SEED)
    if len(X_normal) > LOF_FIT_CAP:
        idx = rng.choice(len(X_normal), LOF_FIT_CAP, replace=False)
        X_lof = X_normal[idx]
    else:
        X_lof = X_normal

    out = {}

    pca = PCA(n_components=5, random_state=SEED).fit(X_normal)
    out['PCA'] = np.mean((X_te - pca.inverse_transform(pca.transform(X_te))) ** 2, axis=1)

    lof = LocalOutlierFactor(n_neighbors=20, contamination=r, novelty=True).fit(X_lof)
    out['LOF'] = -lof.score_samples(X_te)

    # IF as the paper configures it, and as [2] configures it
    inf = IsolationForest(n_estimators=100, contamination=r, random_state=SEED).fit(X_normal)
    out['IF'] = -inf.score_samples(X_te)

    inf_full = IsolationForest(n_estimators=100, max_samples=1.0, contamination=r,
                               random_state=SEED).fit(X_tr)
    out['IF (max_samples=1.0, all training)'] = -inf_full.score_samples(X_te)

    # PCA with a component count suited to the dataset
    k = min(200, X.shape[1] - 1, len(X_normal) - 1)
    if k > 5:
        pca_k = PCA(n_components=k, random_state=SEED).fit(X_normal)
        out[f'PCA ({k} comp.)'] = np.mean(
            (X_te - pca_k.inverse_transform(pca_k.transform(X_te))) ** 2, axis=1)

    return out, y_te, r


if __name__ == '__main__':
    chosen = sys.argv[1:] or list(DATASETS)
    for dataset in chosen:
        scores, y_te, r = scores_for(dataset)
        print(f'\n=== {dataset} (test r = {r * 100:.2f}%, {len(y_te)} units) ===')
        print('Model\tP\tR\tF1\tPR AUC')
        for name, s in scores.items():
            label = f'{name} (oracle)' if name in ('PCA', 'LOF', 'IF') else name
            _, p, rc, f, ap = row(label, y_te, s, r)
            print(f'{label}\t{p:.3f}\t{rc:.3f}\t{f:.3f}\t{ap:.3f}')
        print('\nNote: at the oracle threshold P, R and F1 coincide when the number')
        print('flagged equals the number of anomalies, which is the usual case here.')
