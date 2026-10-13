"""Extra experiments for the LogSense paper.

Run from the repository root (the folder that contains src/ and data/):
    python extra_experiments.py

Needs the feature files already created by notebooks 03-06:
    data/features/X_counts_full.npy   (raw event counts)
    data/features/X_full.npy          (TF-IDF weights)
    data/features/y_full.npy          (labels)

Part 1: repeats the HDFS comparison over 5 random splits and reports mean +- std.
Part 2: checks whether the events shown in the explanation are the ones that
        actually caused PCA to flag the session (a "deletion" test).
"""
import sys
import time

import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.model_selection import train_test_split

sys.path.append('.')
from src.models import run_isolation_forest, run_lof, run_pca

SEEDS = [42, 1, 2, 3, 4]
X_counts = np.load('data/features/X_counts_full.npy')
X_tfidf = np.load('data/features/X_full.npy')
y = np.load('data/features/y_full.npy')
contamination = float(y.mean())


# ---------------------------------------------------------------------------
# Part 1: five random splits
# ---------------------------------------------------------------------------
def run_all(X, seed):
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.3, stratify=y, random_state=seed)
    X_train_normal = X_train[y_train == 0]
    rng = np.random.default_rng(seed)
    lof_idx = rng.choice(len(X_train_normal), size=50_000, replace=False)
    return [
        run_pca(X_train_normal, X_test, y_test, contamination),
        run_lof(X_train_normal[lof_idx], X_test, y_test, contamination),
        run_isolation_forest(X_train_normal, X_test, y_test, contamination),
    ]


rows = []
for features, X in [('Raw counts', X_counts), ('TF-IDF', X_tfidf)]:
    for seed in SEEDS:
        start = time.time()
        for result in run_all(X, seed):
            result.update({'Features': features, 'Seed': seed})
            rows.append(result)
        print(f'{features} seed {seed} done in {time.time() - start:.0f}s')

runs = pd.DataFrame(rows)
runs.to_csv('results/comparison_seeds.csv', index=False)

summary = (runs.groupby(['Features', 'Model'])[['Precision', 'Recall', 'F1', 'PR_AUC']]
           .agg(['mean', 'std']).round(3))
print('\n=== PART 1: mean and std over 5 splits ===')
print(summary.to_string())
summary.to_csv('results/comparison_seeds_summary.csv')


# ---------------------------------------------------------------------------
# Part 2: explanation deletion test (PCA, raw counts, main split)
# ---------------------------------------------------------------------------
X_train, X_test, y_train, y_test = train_test_split(
    X_counts, y, test_size=0.3, stratify=y, random_state=42)
X_train_normal = X_train[y_train == 0]

pca = PCA(n_components=5, random_state=42).fit(X_train_normal)


def pca_error(X):
    return np.mean((X - pca.inverse_transform(pca.transform(X))) ** 2, axis=1)


errors = pca_error(X_test)
threshold = np.percentile(errors, 100 * (1 - contamination))  # same as run_pca
flagged = errors > threshold
true_positives = X_test[flagged & (y_test == 1)]

# Same baseline as src/explain.py: average counts of normal sessions
baseline = X_train_normal.mean(axis=0)
deviation = true_positives - baseline

rng = np.random.default_rng(42)
print(f'\n=== PART 2: explanation deletion test on {len(true_positives)} detected anomalies ===')
print('Share of detected anomalies that are no longer flagged after the k events are set to the baseline')
part2 = []
for k in [1, 3, 5]:
    # Events the explanation would show: largest |observed - baseline|
    top_idx = np.argsort(-np.abs(deviation), axis=1)[:, :k]
    fixed = true_positives.copy()
    rows_idx = np.arange(len(fixed))[:, None]
    fixed[rows_idx, top_idx] = baseline[top_idx]
    top_share = float(np.mean(pca_error(fixed) <= threshold))

    # Control: k random events that also differ from the baseline
    random_shares = []
    for _ in range(10):
        fixed = true_positives.copy()
        for i in range(len(fixed)):
            candidates = np.flatnonzero(np.abs(deviation[i]) > 0)
            pick = rng.choice(candidates, size=min(k, len(candidates)), replace=False)
            fixed[i, pick] = baseline[pick]
        random_shares.append(np.mean(pca_error(fixed) <= threshold))
    random_share = float(np.mean(random_shares))

    part2.append({'k': k, 'Explanation events': round(top_share, 3),
                  'Random events': round(random_share, 3)})
    print(f'  k={k}: explanation events {top_share:.3f} | random events {random_share:.3f}')

pd.DataFrame(part2).to_csv('results/explanation_deletion.csv', index=False)
print('\nSaved results/comparison_seeds.csv, comparison_seeds_summary.csv, explanation_deletion.csv')
