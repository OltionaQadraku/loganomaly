import json
import re
from collections import Counter

import joblib
import numpy as np

from src.parser import HDFS_PATTERN, BGL_PATTERN, extract_block_id, build_miner
from src.explain import explain_session
from src.diagnose import diagnose
from src.narrate import narrate, get_cause_info

HDFS_LINE_EXAMPLE = (
    '081109 203607 169 INFO dfs.DataNode$DataXceiver: Receiving block '
    'blk_-4542486744283261479 src: /10.251.30.179:33720 dest: /10.251.30.179:50010'
)

BGL_LINE_EXAMPLE = (
    '- 1117838570 2005.06.03 R02-M1-N0-C:J12-U11 2005-06-03-15.42.50.675872 '
    'R02-M1-N0-C:J12-U11 RAS KERNEL INFO instruction cache parity error corrected'
)
FORMAT_GUESSES = {
    'apache': re.compile(
        r'^\S+ \S+ \S+ \[.*?\] "\S+ \S+ \S+" \d{3} \S+'),
    'syslog': re.compile(
        r'^\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}\s+\S+\s+\S+:'),
    'json_lines': re.compile(r'^\s*\{.*\}\s*$'),
    'hdfs': HDFS_PATTERN,
    'bgl': BGL_PATTERN,
}

SKIPPED_RATIO_WARNING = 0.2
UNKNOWN_EVENT_RATIO_WARNING = 0.3
SAMPLE_LINE_COUNT = 3


def guess_format(sample_lines):
    """Best-effort guess at the log format of lines that didn't match the
    active pattern."""
    non_empty = [line for line in sample_lines if line.strip()]
    if not non_empty:
        return None
    for name, pattern in FORMAT_GUESSES.items():
        matches = sum(1 for line in non_empty if pattern.match(line.strip()))
        if matches / len(non_empty) > 0.5:
            return name
    return None


class BaseDetectionPipeline:
    """Loads the trained artefacts once and analyses uploaded log files.

    Shared across log types: loading model artefacts, turning a group of
    records into a count vector, scoring with PCA/Isolation Forest/LOF, and
    the overall analyze() orchestration. Each log type only needs to supply
    how to parse its lines, how to group records into analysis units
    (HDFS sessions vs. BGL windows), and how to diagnose a flagged unit's
    likely cause.
    """

    LOG_TYPE = None
    LINE_EXAMPLE = None

    def __init__(self, models_dir, config_path, drain_state_path):
        with open(f'{models_dir}/metadata.json') as f:
            self.metadata = json.load(f)

        self.event_names = self.metadata['event_names']
        self.event_index = {e: i for i, e in enumerate(self.event_names)}
        self.templates = {int(k): (v if isinstance(v, str) else '(empty message)')
                           for k, v in self.metadata['templates'].items()}
        self.pca_threshold = self.metadata['pca_threshold']

        self.baseline = np.load(f'{models_dir}/baseline.npy')
        self.models = {
            'pca': joblib.load(f'{models_dir}/pca.joblib'),
            'isolation_forest': joblib.load(f'{models_dir}/isolation_forest.joblib'),
            'lof': joblib.load(f'{models_dir}/lof.joblib'),
        }
        self.miner = build_miner(config_path, drain_state_path)

    def parse(self, text):
        """Parse raw log text into structured records. Must be overridden."""
        raise NotImplementedError

    def group_units(self, records):
        """Group records into the units anomalies are detected on (HDFS
        sessions, BGL windows, ...). Returns {unit_id: [records]}."""
        raise NotImplementedError

    def diagnose_cause(self, explanation, unit_records, volume_ratio):
        """Turn excess/missing evidence for one flagged unit into a ranked
        list of likely causes. Must be overridden."""
        raise NotImplementedError

    def format_unit_id(self, key):
        return str(key)

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

    def vectorize(self, unit_records):
        """Turn one unit's records into a count vector using the trained event order."""
        vector = np.zeros(len(self.event_names))
        for record in unit_records:
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
            log_type_name = self.LOG_TYPE.upper()
            message = f'No lines matched the expected {log_type_name} log format.'
            if guessed and guessed != self.LOG_TYPE:
                message = (f"This looks like a {guessed.replace('_', ' ')} log, "
                            f"not a {log_type_name}-style log. This endpoint "
                            f"currently only analyses {log_type_name}-format logs.")
            return {'error': message,
                    'skipped_lines': skipped,
                    'sample_lines': sample_skipped,
                    'guessed_format': guessed}

        unknown = self.assign_events(records)
        units = self.group_units(records)
        keys = list(units)

        matrix = np.vstack([self.vectorize(units[k]) for k in keys])
        scores, flags = self.score(matrix, model_name)

        lengths = np.array([len(units[k]) for k in keys])
        mean_length = lengths.mean() or 1

        anomalies = []
        cause_counts = Counter()

        for i, key in enumerate(keys):
            if not flags[i]:
                continue
            explanation = explain_session(matrix[i], self.baseline, self.event_names)
            diagnosis = self.diagnose_cause(explanation, units[key],
                                             float(lengths[i] / mean_length))
            cause_counts[diagnosis['primary_cause']] += 1
            unit_id = self.format_unit_id(key)
            cause_info = get_cause_info(diagnosis['primary_cause'])
            anomalies.append({
                'session_id': unit_id,
                'score': round(float(scores[i]), 6),
                'event_count': int(lengths[i]),
                'primary_cause': diagnosis['primary_cause'],
                'title': cause_info['title'],
                'severity': cause_info['severity'],
                'all_causes': diagnosis['all_causes'],
                'report': narrate(explanation, diagnosis, self.templates, unit_id),
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
                f"expected {self.LOG_TYPE.upper()} format and were skipped.")
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
            'log_type': self.LOG_TYPE,
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


class HDFSDetectionPipeline(BaseDetectionPipeline):
    """HDFS: sessions are grouped by BlockId; cause diagnosis is keyword-rule-based."""

    LOG_TYPE = 'hdfs'
    LINE_EXAMPLE = HDFS_LINE_EXAMPLE

    def __init__(self, models_dir='models', config_path='drain3.ini'):
        super().__init__(models_dir, config_path, f'{models_dir}/drain_state_full.bin')

    def parse(self, text):
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

    def group_units(self, records):
        sessions = {}
        for record in records:
            key = record['BlockId'] or 'unassigned'
            sessions.setdefault(key, []).append(record)
        return sessions

    def diagnose_cause(self, explanation, unit_records, volume_ratio):
        return diagnose(explanation, self.templates, volume_ratio=volume_ratio)


class BGLDetectionPipeline(BaseDetectionPipeline):
    """BGL: no natural session ID, so records are grouped into fixed-size
    tumbling windows (matching how the models were trained). Cause diagnosis
    uses a classifier trained on real per-line fault-category labels,
    instead of keyword rules."""

    LOG_TYPE = 'bgl'
    LINE_EXAMPLE = BGL_LINE_EXAMPLE
    WINDOW_SIZE = 100

    def __init__(self, models_dir='models/bgl', config_path='drain3_bgl.ini',
                 drain_state_path='models/bgl_drain_state_full.bin'):
        super().__init__(models_dir, config_path, drain_state_path)
        self.cause_classifier = joblib.load(f'{models_dir}/cause_classifier.joblib')

    def parse(self, text):
        records, skipped, sample_skipped = [], 0, []
        for line in text.splitlines():
            stripped = line.strip()
            match = BGL_PATTERN.match(stripped)
            if not match:
                skipped += 1
                if stripped and len(sample_skipped) < SAMPLE_LINE_COUNT:
                    sample_skipped.append(stripped[:200])
                continue
            records.append(match.groupdict())
        return records, skipped, sample_skipped

    def group_units(self, records):
        windows = {}
        for i, record in enumerate(records):
            key = i // self.WINDOW_SIZE
            windows.setdefault(key, []).append(record)
        return windows

    def format_unit_id(self, key):
        return f'window-{key}'

    def diagnose_cause(self, explanation, unit_records, volume_ratio):
       
        content_by_event = {}
        for record in unit_records:
            content_by_event.setdefault(record['EventId'], record['content'])

        votes = Counter()
        evidence = []
        for item in explanation['excess']:
            content = content_by_event.get(item['event'])
            if not content:
                continue
            predicted = self.cause_classifier.predict([content])[0]
            votes[predicted] += item['deviation']
            evidence.append(f"\"{content[:80]}\" occurred {item['observed']:.0f}x "
                             f"-> classified as {predicted}")

        ranked = sorted(votes.items(), key=lambda kv: -kv[1])
        return {
            'primary_cause': ranked[0][0] if ranked else 'UNKNOWN',
            'all_causes': [c for c, _ in ranked],
            'evidence': evidence,
        }


PIPELINE_CLASSES = {
    'hdfs': HDFSDetectionPipeline,
    'bgl': BGLDetectionPipeline,
}

DetectionPipeline = HDFSDetectionPipeline
