import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfTransformer


def build_sessions(df):
    """Group log lines by block ID into event sequences."""
    df = df.dropna(subset=['BlockId'])
    sessions = df.groupby('BlockId')['EventId'].apply(list)
    return sessions.reset_index(name='EventSequence')


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