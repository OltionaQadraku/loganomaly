import json
import re
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

HDFS_LINE_EXAMPLE = (
    '081109 203607 169 INFO dfs.DataNode$DataXceiver: Receiving block '
    'blk_-4542486744283261479 src: /10.251.30.179:33720 dest: /10.251.30.179:50010'
)

FORMAT_GUESSES = {
    'apache': re.compile(
        r'^\S+ \S+ \S+ \[.*?\] "\S+ \S+ \S+" \d{3} \S+'),
    'syslog': re.compile(
        r'^\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}\s+\S+\s+\S+:'),
    'json_lines': re.compile(r'^\s*\{.*\}\s*$'),
}

SKIPPED_RATIO_WARNING = 0.2
UNKNOWN_EVENT_RATIO_WARNING = 0.3
SAMPLE_LINE_COUNT = 3


def guess_format(sample_lines):
    """Best-effort guess at the log format of lines that didn't match HDFS_PATTERN."""
    non_empty = [line for line in sample_lines if line.strip()]
    if not non_empty:
        return None
    for name, pattern in FORMAT_GUESSES.items():
        matches = sum(1 for line in non_empty if pattern.match(line.strip()))
        if matches / len(non_empty) > 0.5:
            return name
    return None


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
        self.miner = build_miner(config_path, f'{models_dir}/drain_state_full.bin')

    def parse(self, text):
        """Parse raw log text into structured records."""
        records, skipped, sample_skipped = [], 0, []
        for line in text.splitlines():
            stripped = line.strip()
            match = HDFS_PATTERN.match(stripped)
            if not match:
                skipped += 1
                if stripped and len(sample_skipped) < SAMPLE_LINE_COUNT:
                    sample_skipped.append(stripped[:200])
                continue
            record = match.groupdict()
            record['BlockId'] = extract_block_id(record['content'])
            records.append(record)
        return records, skipped, sample_skipped

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
        records, skipped, sample_skipped = self.parse(text)
        if not records:
            guessed = guess_format(sample_skipped)
            message = 'No lines matched the expected HDFS log format.'
            if guessed:
                message = (f"This looks like a {guessed.replace('_', ' ')} log, "
                            f"not an HDFS-style log. LogSense currently only "
                            f"analyses HDFS-format logs.")
            return {'error': message,
                    'skipped_lines': skipped,
                    'sample_lines': sample_skipped,
                    'guessed_format': guessed}

        unknown = self.assign_events(records)
        sessions = self.build_sessions(records)
        keys = list(sessions)

        matrix = np.vstack([self.vectorize(sessions[k]) for k in keys])
        scores, flags = self.score(matrix, model_name)
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

        total_lines = len(records) + skipped
        warnings = []
        skipped_ratio = skipped / total_lines if total_lines else 0
        if skipped_ratio > SKIPPED_RATIO_WARNING:
            warnings.append(
                f"{round(skipped_ratio * 100)}% of lines did not match the "
                f"expected HDFS format and were skipped.")
        unknown_ratio = unknown / len(records) if records else 0
        if unknown_ratio > UNKNOWN_EVENT_RATIO_WARNING:
            warnings.append(
                f"{round(unknown_ratio * 100)}% of log events are unrecognised "
                f"by the trained model — results may be less accurate.")

        message = ('Analysis completed successfully — no anomalous sessions '
                    'were found in this file.' if not anomalies else
                    f'Analysis completed successfully — {len(anomalies)} '
                    f'anomalous session(s) found out of {len(keys)}.')

        return {
            'model': model_name,
            'message': message,
            'total_lines': len(records),
            'skipped_lines': skipped,
            'unknown_events': unknown,
            'total_sessions': len(keys),
            'anomalies_found': len(anomalies),
            'anomaly_rate': round(len(anomalies) / len(keys) * 100, 2),
            'cause_distribution': dict(cause_counts),
            'warnings': warnings,
            'anomalies': anomalies,
        }