"""Realistic (label-free) threshold for PCA on BGL.

This is the number missing from Table 2. The application sets its threshold from
the scores of the NORMAL TRAINING data, never from the test set, so this is the
figure that is comparable with the LOF and IF rows.

Run from the repository root (same place as paper_numbers.py):
    python bgl_threshold.py

Needs the feature files created by notebook 12:
    data/features/X_counts_full_bgl.npy
    data/features/y_full_bgl.npy
"""
import numpy as np
from sklearn.decomposition import PCA
from sklearn.metrics import (average_precision_score, f1_score,
                             precision_score, recall_score)
from sklearn.model_selection import train_test_split

X = np.load('data/features/X_counts_full_bgl.npy')
y = np.load('data/features/y_full_bgl.npy')
contamination = float(y.mean())

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.3, stratify=y, random_state=42)
X_train_normal = X_train[y_train == 0]

pca = PCA(n_components=5, random_state=42).fit(X_train_normal)


def error(data):
    """Mean squared reconstruction error, the same score the application uses."""
    return np.mean((data - pca.inverse_transform(pca.transform(data))) ** 2, axis=1)


# the realistic threshold: a percentile of the normal TRAINING scores, no test labels
threshold = np.percentile(error(X_train_normal), 100 * (1 - contamination))

scores = error(X_test)
pred = (scores > threshold).astype(int)

print('=== BGL, PCA, realistic threshold ===')
print(f'anomaly rate r          : {contamination * 100:.2f}%')
print(f'percentile used         : {100 * (1 - contamination):.2f}th of normal training scores')
print(f'threshold               : {threshold:.6f}')
print(f'flagged                 : {pred.sum()} of {len(pred)} test windows '
      f'({100 * pred.mean():.2f}%)')
print()
print(f'P      = {precision_score(y_test, pred, zero_division=0):.3f}')
print(f'R      = {recall_score(y_test, pred, zero_division=0):.3f}')
print(f'F1     = {f1_score(y_test, pred, zero_division=0):.3f}')
print(f'PR AUC = {average_precision_score(y_test, scores):.3f}   '
      '(sanity check: this should come out 0.718)')
