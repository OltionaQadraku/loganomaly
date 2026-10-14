"""Experiments requested by the LogSense review.

Run from the repository root, same place as paper_numbers.py:

    python extra_experiments.py            # all experiments
    python extra_experiments.py if_config  # one experiment by name

Needs the feature files created by notebooks 03-06 (HDFS) and 12 (BGL):
    data/features/X_counts_full.npy       data/features/y_full.npy
    data/features/X_counts_full_bgl.npy   data/features/y_full_bgl.npy

Every printed line is tagged with the paper slot it fills, written as
[A1], [A2], ... so the numbers can be copied straight into the manuscript.
"""
import sys
import time

import numpy as np
from sklearn.decomposition import PCA
from sklearn.ensemble import IsolationForest
from sklearn.metrics import average_precision_score, f1_score, precision_score, recall_score
from sklearn.model_selection import train_test_split

sys.path.append('.')

SEED = 42
LOF_SAMPLE = 50_000  # LOF is fitted on a subsample, as in the paper
HDFS = ('data/features/X_counts_full.npy', 'data/features/y_full.npy')
BGL = ('data/features/X_counts_full_bgl.npy', 'data/features/y_full_bgl.npy')


def load(paths):
    return np.load(paths[0]), np.load(paths[1])


def split(X, y, seed=SEED):
    X_tr, X_te, y_tr, y_te = train_test_split(
        X, y, test_size=0.3, stratify=y, random_state=seed)
    return X_tr[y_tr == 0], X_te, y_te


def pca_errors(model, data):
    return np.mean((data - model.inverse_transform(model.transform(data))) ** 2, axis=1)


def prf(y_true, pred):
    return (precision_score(y_true, pred, zero_division=0),
            recall_score(y_true, pred, zero_division=0),
            f1_score(y_true, pred, zero_division=0))


# ---------------------------------------------------------------------------
# A. Isolation Forest: is the near-random result caused by the configuration?
# ---------------------------------------------------------------------------
def if_config():
    """Reviewer point 1. Separates three candidate causes of IF's PR AUC.

    Cause 1  max_samples=256 default (each tree sees a tiny subsample)
    Cause 2  normal-only training (loglizer fits on normal + anomalous)
    Cause 3  neither, IF simply cannot rank these anomalies

    If row 'max_samples=1.0, normal-only' stays near random while
    'max_samples=1.0, all data' jumps, the cause is the training regime.
    If both stay near random, the cause is the detector on this geometry
    and the paper's current configuration explanation must be replaced.
    """
    print('\n=== [A] Isolation Forest configuration sweep ===')
    for name, paths in (('HDFS', HDFS), ('BGL', BGL)):
        X, y = load(paths)
        X_tr, X_te, y_tr, y_te = train_test_split(
            X, y, test_size=0.3, stratify=y, random_state=SEED)
        X_tr_normal = X_tr[y_tr == 0]
        contamination = float(y.mean())
        print(f'\n-- {name} (random PR AUC = {y_te.mean():.3f}) --')

        settings = [
            ('max_samples=256,  normal-only', X_tr_normal, y_tr[y_tr == 0], 256),
            ('max_samples=1.0,  normal-only', X_tr_normal, y_tr[y_tr == 0], 1.0),
            ('max_samples=256,  all training', X_tr, y_tr, 256),
            ('max_samples=1.0,  all training', X_tr, y_tr, 1.0),
        ]
        for label, Xt, _, max_samples in settings:
            ms = min(max_samples, len(Xt)) if isinstance(max_samples, int) else max_samples
            model = IsolationForest(n_estimators=100, max_samples=ms,
                                    contamination=contamination, random_state=SEED)
            model.fit(Xt)
            scores = -model.score_samples(X_te)
            pred = (model.predict(X_te) == -1).astype(int)
            p, r, f = prf(y_te, pred)
            ap = average_precision_score(y_te, scores)
            print(f'  [A1] {label:<32} PR AUC={ap:.3f}  P={p:.3f} R={r:.3f} F1={f:.3f}')

        # Is the failure about axis-aligned splits rather than configuration?
        # A marginal-extremity baseline scores a unit by how far its single
        # most unusual count is from the normal range. If it matches IF, IF is
        # only seeing marginals and the anomalies are combination anomalies.
        lo = np.percentile(X_tr_normal, 1, axis=0)
        hi = np.percentile(X_tr_normal, 99, axis=0)
        spread = np.maximum(hi - lo, 1e-9)
        marginal = np.max(np.maximum((X_te - hi) / spread, (lo - X_te) / spread), axis=1)
        print(f'  [A2] marginal-extremity baseline    '
              f'PR AUC={average_precision_score(y_te, marginal):.3f}')


# ---------------------------------------------------------------------------
# B. Explanation: rank events by contribution to the PCA error, not by deviation
# ---------------------------------------------------------------------------
def explanation():
    """Reviewer point 2. Current ranking is |observed - baseline|.

    For PCA the reconstruction error decomposes per feature, so the exact
    drop in score obtained by resetting feature i to its baseline value can
    be measured directly. This ranks events by effect on the decision rather
    than by raw size of deviation, which is what the reset test rewards.
    """
    print('\n=== [B] Explanation faithfulness, deviation vs contribution ===')
    X, y = load(HDFS)
    X_tr, X_te, y_tr, y_te = train_test_split(
        X, y, test_size=0.3, stratify=y, random_state=SEED)
    X_tr_normal = X_tr[y_tr == 0]
    pca = PCA(n_components=5, random_state=SEED).fit(X_tr_normal)
    baseline = X_tr_normal.mean(axis=0)

    errors = pca_errors(pca, X_te)
    r = float(y.mean())
    oracle_thr = np.percentile(errors, 100 * (1 - r))
    flagged = np.where(errors > oracle_thr)[0]
    print(f'  anomalies flagged at oracle threshold: {len(flagged)}')

    rng = np.random.default_rng(SEED)

    def reset_drop(idx, k, strategy):
        """Reset k events of unit idx to baseline, return True if alarm cleared."""
        x = X_te[idx].copy()
        dev = x - baseline
        if strategy == 'deviation':
            order = np.argsort(-np.abs(dev))
        elif strategy == 'contribution':
            # Exact drop in mean squared reconstruction error obtained by
            # resetting each feature on its own. Built as one matrix of
            # single-feature resets so the whole ranking costs one transform.
            variants = np.repeat(x.reshape(1, -1), len(x), axis=0)
            variants[np.arange(len(x)), np.arange(len(x))] = baseline
            drops = errors[idx] - pca_errors(pca, variants)
            drops[np.abs(dev) < 1e-12] = 0.0
            order = np.argsort(-drops)
        else:  # random control, drawn from events differing from baseline
            candidates = np.where(np.abs(dev) > 1e-12)[0]
            if len(candidates) == 0:
                return False
            order = rng.permutation(candidates)
        chosen = order[:k]
        x[chosen] = baseline[chosen]
        return pca_errors(pca, x.reshape(1, -1))[0] <= oracle_thr

    for k in (1, 3, 5):
        row = {}
        for strategy in ('deviation', 'contribution'):
            cleared = sum(reset_drop(i, k, strategy) for i in flagged)
            row[strategy] = 100 * cleared / len(flagged)
        # random control, ten draws, reported with a 95% interval
        draws = [100 * sum(reset_drop(i, k, 'random') for i in flagged) / len(flagged)
                 for _ in range(10)]
        mean, sd = float(np.mean(draws)), float(np.std(draws, ddof=1))
        ci = 1.96 * sd / np.sqrt(len(draws))
        print(f'  [B1] k={k}  deviation={row["deviation"]:.1f}%  '
              f'contribution={row["contribution"]:.1f}%  '
              f'random={mean:.1f}% +/- {ci:.1f}')


# ---------------------------------------------------------------------------
# C. Chronological split instead of random
# ---------------------------------------------------------------------------
def chronological():
    """Reviewer point 3. Rows are in file order, so the first 70% is the past.

    This is the split a deployment actually faces. A large drop here is the
    honest number and belongs in the paper even if it is worse.
    """
    print('\n=== [C] Chronological split (first 70% train, last 30% test) ===')
    for name, paths in (('HDFS', HDFS), ('BGL', BGL)):
        X, y = load(paths)
        cut = int(0.7 * len(X))
        X_tr, y_tr = X[:cut], y[:cut]
        X_te, y_te = X[cut:], y[cut:]
        X_tr_normal = X_tr[y_tr == 0]
        if len(X_tr_normal) == 0 or y_te.sum() == 0:
            print(f'  {name}: split leaves no normal training data or no test anomalies')
            continue
        r = float(y_tr.mean())
        pca = PCA(n_components=5, random_state=SEED).fit(X_tr_normal)
        err_tr = pca_errors(pca, X_tr_normal)
        err_te = pca_errors(pca, X_te)
        thr = np.percentile(err_tr, 100 * (1 - r))
        p, rc, f = prf(y_te, (err_te > thr).astype(int))
        ap = average_precision_score(y_te, err_te)
        print(f'  [C1] {name} PCA  PR AUC={ap:.3f}  P={p:.3f} R={rc:.3f} F1={f:.3f}  '
              f'(random PR AUC={y_te.mean():.3f})')


# ---------------------------------------------------------------------------
# D. PCA component sweep, especially for BGL with 1,124 templates
# ---------------------------------------------------------------------------
def components():
    """Reviewer point 4. Five components for 1,124 templates needs justifying."""
    print('\n=== [D] PCA component sweep ===')
    for name, paths in (('HDFS', HDFS), ('BGL', BGL)):
        X, y = load(paths)
        X_tr_normal, X_te, y_te = split(X, y)
        r = float(y.mean())
        n_max = min(X.shape[1], len(X_tr_normal))
        grid = [k for k in (2, 5, 10, 20, 50, 100, 200) if k < n_max]
        print(f'\n-- {name} ({X.shape[1]} templates) --')
        for k in grid:
            pca = PCA(n_components=k, random_state=SEED).fit(X_tr_normal)
            err_tr = pca_errors(pca, X_tr_normal)
            err_te = pca_errors(pca, X_te)
            thr = np.percentile(err_tr, 100 * (1 - r))
            p, rc, f = prf(y_te, (err_te > thr).astype(int))
            ap = average_precision_score(y_te, err_te)
            ev = pca.explained_variance_ratio_.sum() * 100
            print(f'  [D1] k={k:<4} var={ev:5.2f}%  PR AUC={ap:.3f}  F1={f:.3f}')


# ---------------------------------------------------------------------------
# E. Sensitivity of the realistic threshold to a misestimated anomaly rate r
# ---------------------------------------------------------------------------
def r_sensitivity():
    """Reviewer point 5. The paper uses the true rate, a deployment guesses it."""
    print('\n=== [E] Sensitivity to a misestimated anomaly rate r ===')
    for name, paths in (('HDFS', HDFS), ('BGL', BGL)):
        X, y = load(paths)
        X_tr_normal, X_te, y_te = split(X, y)
        true_r = float(y.mean())
        pca = PCA(n_components=5, random_state=SEED).fit(X_tr_normal)
        err_tr = pca_errors(pca, X_tr_normal)
        err_te = pca_errors(pca, X_te)
        print(f'\n-- {name} (true r = {true_r * 100:.2f}%) --')
        for factor in (0.5, 0.75, 1.0, 1.5, 2.0):
            r = min(true_r * factor, 0.99)
            thr = np.percentile(err_tr, 100 * (1 - r))
            p, rc, f = prf(y_te, (err_te > thr).astype(int))
            print(f'  [E1] r x {factor:<4} ({r * 100:5.2f}%)  '
                  f'P={p:.3f} R={rc:.3f} F1={f:.3f}')


# ---------------------------------------------------------------------------
# F. Repeat over five random splits, for BGL as well as HDFS
# ---------------------------------------------------------------------------
def splits():
    """Reviewer minor point. The paper reports +/- only for HDFS."""
    print('\n=== [F] Five random splits ===')
    from src.models import run_lof, run_pca
    for name, paths in (('HDFS', HDFS), ('BGL', BGL)):
        X, y = load(paths)
        contamination = float(y.mean())
        acc = {'PCA': [], 'LOF': []}
        for seed in (0, 1, 2, 3, 4):
            X_tr_normal, X_te, y_te = split(X, y, seed=seed)
            acc['PCA'].append(run_pca(X_tr_normal, X_te, y_te, contamination)['PR_AUC'])
            if len(X_tr_normal) > LOF_SAMPLE:
                rng = np.random.default_rng(seed)
                X_lof = X_tr_normal[rng.choice(len(X_tr_normal), LOF_SAMPLE, replace=False)]
            else:
                X_lof = X_tr_normal
            acc['LOF'].append(run_lof(X_lof, X_te, y_te, contamination)['PR_AUC'])
        for model, values in acc.items():
            v = np.array(values, dtype=float)
            print(f'  [F1] {name} {model}  PR AUC = {v.mean():.3f} +/- {v.std(ddof=1):.3f}')


EXPERIMENTS = {
    'if_config': if_config,
    'explanation': explanation,
    'chronological': chronological,
    'components': components,
    'r_sensitivity': r_sensitivity,
    'splits': splits,
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
