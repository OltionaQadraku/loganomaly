"""Numbers for the yellow [XX] placeholders in the LogSense paper.

Run from the repository root (same place as extra_experiments.py):
    python paper_numbers.py

Needs the feature files created by notebooks 03-06 (HDFS) and 12 (BGL):
    data/features/X_counts_full.npy, data/features/y_full.npy
    data/features/X_counts_full_bgl.npy, data/features/y_full_bgl.npy
"""
import sys

import numpy as np
from sklearn.decomposition import PCA
from sklearn.metrics import f1_score, precision_score, recall_score
from sklearn.model_selection import train_test_split

sys.path.append('.')
from src.models import run_isolation_forest, run_lof, run_pca

# ---------------------------------------------------------------------------
# 1) HDFS: explained variance of 5 PCA components + label-free 97th percentile threshold
# ---------------------------------------------------------------------------
X = np.load('data/features/X_counts_full.npy')
y = np.load('data/features/y_full.npy')
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.3, stratify=y, random_state=42)
X_train_normal = X_train[y_train == 0]

pca = PCA(n_components=5, random_state=42).fit(X_train_normal)


def pca_error(data):
    return np.mean((data - pca.inverse_transform(pca.transform(data))) ** 2, axis=1)


threshold = np.percentile(pca_error(X_train_normal), 97)  # same rule as the application
pred = (pca_error(X_test) > threshold).astype(int)

print('=== HDFS ===')
print(f'Explained variance (5 components): {pca.explained_variance_ratio_.sum() * 100:.1f}%')
print('Label-free threshold (97th percentile of normal training errors):')
print(f'  P={precision_score(y_test, pred):.3f}  R={recall_score(y_test, pred):.3f}  '
      f'F1={f1_score(y_test, pred):.3f}  flagged={pred.sum()}')

# ---------------------------------------------------------------------------
# 2) BGL: same protocol as the HDFS comparison (raw counts, 70/30 split, seed 42)
# ---------------------------------------------------------------------------
Xb = np.load('data/features/X_counts_full_bgl.npy')
yb = np.load('data/features/y_full_bgl.npy')
contamination = float(yb.mean())
Xb_train, Xb_test, yb_train, yb_test = train_test_split(
    Xb, yb, test_size=0.3, stratify=yb, random_state=42)
Xb_train_normal = Xb_train[yb_train == 0]

print('\n=== BGL (raw counts) ===')
print(f'Test windows: {len(yb_test)} | anomalous: {int(yb_test.sum())} | '
      f'random PR AUC ~ {yb_test.mean():.3f}')
for result in [run_pca(Xb_train_normal, Xb_test, yb_test, contamination),
               run_lof(Xb_train_normal, Xb_test, yb_test, contamination),
               run_isolation_forest(Xb_train_normal, Xb_test, yb_test, contamination)]:
    print(f"  {result['Model']:<22} P={result['Precision']:.3f}  R={result['Recall']:.3f}  "
          f"F1={result['F1']:.3f}  PR_AUC={result['PR_AUC']:.3f}")
