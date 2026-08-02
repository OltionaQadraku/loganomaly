import numpy as np


def build_baseline(X_counts, y):
    """Average event profile across normal sessions."""
    return X_counts[y == 0].mean(axis=0)


def explain_session(session_counts, baseline, event_names, min_deviation=0.5, top_n=5):
    """Compare one session against the normal profile."""
    deviation = session_counts - baseline

    excess = [
        {'event': event_names[i],
         'observed': float(session_counts[i]),
         'expected': round(float(baseline[i]), 2),
         'deviation': round(float(deviation[i]), 2)}
        for i in np.argsort(-deviation)[:top_n]
        if deviation[i] > min_deviation
    ]

    missing = [
        {'event': event_names[i],
         'observed': float(session_counts[i]),
         'expected': round(float(baseline[i]), 2),
         'deviation': round(float(deviation[i]), 2)}
        for i in np.argsort(deviation)[:top_n]
        if deviation[i] < -min_deviation
    ]

    return {'excess': excess, 'missing': missing}