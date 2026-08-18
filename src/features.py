import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfTransformer


def build_sessions(df):
    """Group log lines by block ID into event sequences."""
    df = df.dropna(subset=['BlockId'])
    sessions = df.groupby('BlockId')['EventId'].apply(list)
    return sessions.reset_index(name='EventSequence')


def build_windows(df, window_size=100):
    """Group consecutive log lines into fixed-size tumbling windows.

    Used for logs (like BGL) that have no natural session ID to group by.
    """
    df = df.reset_index(drop=True).assign(WindowId=lambda d: d.index // window_size)
    windows = df.groupby('WindowId')['EventId'].apply(list)
    return windows.reset_index(name='EventSequence')


def attach_window_labels(windows, df, window_size=100):
    """Merge per-line fault-category labels into the window table.

    A window is anomalous (y=1) if any of its lines carry a label other
    than '-'. `causes` keeps the distinct fault categories present.
    """
    df = df.reset_index(drop=True).assign(WindowId=lambda d: d.index // window_size)

    def summarize(labels):
        causes = sorted({label for label in labels if label != '-'})
        return pd.Series({'y': int(bool(causes)), 'causes': causes})

    summary = df.groupby('WindowId')['label'].apply(list).apply(summarize).reset_index()
    return windows.merge(summary, on='WindowId', how='left')


def attach_labels(sessions, label_path):
    """Merge ground-truth anomaly labels into the session table."""
    labels = pd.read_csv(label_path)
    labels['y'] = (labels['Label'] == 'Anomaly').astype(int)
    return sessions.merge(labels[['BlockId', 'y']], on='BlockId', how='inner')


def count_vector(sessions):
    """Build a matrix where rows are sessions and columns are event counts."""
    all_events = sorted({e for seq in sessions['EventSequence'] for e in seq})
    index = {event: i for i, event in enumerate(all_events)}
    matrix = np.zeros((len(sessions), len(all_events)))
    for row, seq in enumerate(sessions['EventSequence']):
        for event in seq:
            matrix[row, index[event]] += 1
    return matrix, all_events


def apply_tfidf(matrix):
    """Down-weight events that appear in almost every session."""
    return TfidfTransformer().fit_transform(matrix).toarray()