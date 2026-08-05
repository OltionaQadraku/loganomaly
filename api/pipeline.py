import json
from collections import Counter

import joblib
import numpy as np

from src.parser import HDFS_PATTERN, extract_block_id, build_miner
from src.explain import explain_session
from src.diagnose import diagnose
from src.narrate import narrate

MODEL_FILES = {
    'pca': 'models/pca.joblib',
    'isolation_forest': 'models/isolation_forest.joblib',
    'lof': 'models/lof.joblib',
}


class DetectionPipeline:
    """Loads the trained artefacts once and analyses uploaded log files."""

    def __init__(self, models_dir='models', config_path='drain3.ini'):
        with open(f'{models_dir}/metadata.json') as f:
            self.metadata = json.load(f)

        self.event_names = self.metadata['event_names']
        self.event_index = {e: i for i, e in enumerate(self.event_names)}
        self.templates = {int(k): v for k, v in self.metadata['templates'].items()}
        self.pca_threshold = self.metadata['pca_threshold']

        self.baseline = np.load(f'{models_dir}/baseline.npy')
        self.models = {name: joblib.load(path) for name, path in MODEL_FILES.items()}

        # Reuse the parser state from training so event IDs stay consistent
        self.miner = build_miner(config_path, f'{models_dir}/drain_state_full.bin')

    def parse(self, text):
        """Parse raw log text into structured records."""
        records, skipped = [], 0
        for line in text.splitlines():
            match = HDFS_PATTERN.match(line.strip())
            if not match:
                skipped += 1
                continue
            record = match.groupdict()
            record['BlockId'] = extract_block_id(record['content'])
            records.append(record)
        return records, skipped

    def assign_events(self, records):
        """Map each message to a known event ID using the trained parser."""
        unknown = 0
        for record in records:
            cluster = self.miner.match(record['content'])
            if cluster is None:
                record['EventId'] = None
                unknown += 1
            else:
                record['EventId'] = cluster.cluster_id
        return unknown

    def build_sessions(self, records):
        """Group records by session identifier."""
        sessions = {}
        for record in records:
            key = record['BlockId'] or 'unassigned'
            sessions.setdefault(key, []).append(record)
        return sessions

    def vectorize(self, session_records):
        """Turn one session into a count vector using the trained event order."""
        vector = np.zeros(len(self.event_names))
        for record in session_records:
            idx = self.event_index.get(record['EventId'])
            if idx is not None:
                vector[idx] += 1
        return vector

    def score(self, matrix, model_name):
        model = self.models[model_name]
        if model_name == 'pca':
            reconstructed = model.inverse_transform(model.transform(matrix))
            scores = np.mean((matrix - reconstructed) ** 2, axis=1)
            flags = scores > self.pca_threshold
        else:
            scores = -model.score_samples(matrix)
            flags = model.predict(matrix) == -1
        return scores, flags

    def analyze(self, text, model_name='pca'):
        records, skipped = self.parse(text)
        if not records:
            return {'error': 'No lines matched the expected log format.',
                    'skipped_lines': skipped}

        unknown = self.assign_events(records)
        sessions = self.build_sessions(records)
        keys = list(sessions)

        matrix = np.vstack([self.vectorize(sessions[k]) for k in keys])
        scores, flags = self.score(matrix, model_name)

        # Volume relative to the average session, used as the overload signal
        lengths = np.array([len(sessions[k]) for k in keys])
        mean_length = lengths.mean() or 1

        anomalies = []
        cause_counts = Counter()

        for i, key in enumerate(keys):
            if not flags[i]:
                continue
            explanation = explain_session(matrix[i], self.baseline, self.event_names)
            diagnosis = diagnose(explanation, self.templates,
                                 volume_ratio=float(lengths[i] / mean_length))
            cause_counts[diagnosis['primary_cause']] += 1
            anomalies.append({
                'session_id': key,
                'score': round(float(scores[i]), 6),
                'event_count': int(lengths[i]),
                'primary_cause': diagnosis['primary_cause'],
                'all_causes': diagnosis['all_causes'],
                'report': narrate(explanation, diagnosis, self.templates, key),
                'excess': explanation['excess'],
                'missing': explanation['missing'],
            })

        anomalies.sort(key=lambda a: -a['score'])

        return {
            'model': model_name,
            'total_lines': len(records),
            'skipped_lines': skipped,
            'unknown_events': unknown,
            'total_sessions': len(keys),
            'anomalies_found': len(anomalies),
            'anomaly_rate': round(len(anomalies) / len(keys) * 100, 2),
            'cause_distribution': dict(cause_counts),
            'anomalies': anomalies,
        }