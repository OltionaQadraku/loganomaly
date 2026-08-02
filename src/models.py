import time
import numpy as np
import pandas as pd
from sklearn.metrics import (precision_score, recall_score, f1_score,
                             roc_auc_score, confusion_matrix)
from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.neighbors import LocalOutlierFactor
from sklearn.decomposition import PCA
from sklearn.metrics import average_precision_score

def evaluate(y_true, y_pred, scores, name, train_time, infer_time):
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred).ravel()
    return {
        'Model': name,
        'Precision': round(precision_score(y_true, y_pred, zero_division=0), 4),
        'Recall': round(recall_score(y_true, y_pred, zero_division=0), 4),
        'F1': round(f1_score(y_true, y_pred, zero_division=0), 4),
        'ROC_AUC': round(roc_auc_score(y_true, scores), 4) if scores is not None else None,
        'PR_AUC': round(average_precision_score(y_true, scores), 4) if scores is not None else None,
        'FPR': round(fp / (fp + tn), 4) if (fp + tn) else 0,
        'TP': tp, 'FP': fp, 'FN': fn, 'TN': tn,
        'TrainTime': round(train_time, 3),
        'InferTime': round(infer_time, 3),
    }
def run_isolation_forest(X_train, X_test, y_test, contamination):
    start = time.time()
    model = IsolationForest(contamination=contamination, random_state=42)
    model.fit(X_train)
    train_time = time.time() - start

    start = time.time()
    pred = (model.predict(X_test) == -1).astype(int)
    infer_time = time.time() - start

    scores = -model.score_samples(X_test)
    return evaluate(y_test, pred, scores, "Isolation Forest", train_time, infer_time)

def run_lof(X_train, X_test, y_test, contamination, n_neighbors=20):
    start = time.time()
    model = LocalOutlierFactor(n_neighbors=n_neighbors,
                               contamination=contamination, novelty=True)
    model.fit(X_train)
    train_time = time.time() - start

    start = time.time()
    pred = (model.predict(X_test) == -1).astype(int)
    infer_time = time.time() - start

    scores = -model.score_samples(X_test)
    return evaluate(y_test, pred, scores, "Local Outlier Factor", train_time, infer_time)

def run_pca(X_train, X_test, y_test, contamination, n_components=5):
    start = time.time()
    model = PCA(n_components=n_components, random_state=42)
    model.fit(X_train)
    train_time = time.time() - start

    start = time.time()
    reconstructed = model.inverse_transform(model.transform(X_test))
    errors = np.mean((X_test - reconstructed) ** 2, axis=1)
    threshold = np.percentile(errors, 100 * (1 - contamination))
    pred = (errors > threshold).astype(int)
    infer_time = time.time() - start

    return evaluate(y_test, pred, errors, "PCA", train_time, infer_time)

def run_random_forest(X_train, y_train, X_test, y_test):
    start = time.time()
    model = RandomForestClassifier(n_estimators=100, random_state=42,
                                   class_weight='balanced')
    model.fit(X_train, y_train)
    train_time = time.time() - start

    start = time.time()
    pred = model.predict(X_test)
    infer_time = time.time() - start

    scores = model.predict_proba(X_test)[:, 1]
    return evaluate(y_test, pred, scores, "Random Forest", train_time, infer_time)