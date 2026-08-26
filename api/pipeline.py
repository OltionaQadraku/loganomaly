import json
import re
from collections import Counter

import joblib
import numpy as np

from src.parser import (HDFS_PATTERN, BGL_PATTERN, SSH_PATTERN, GENERIC_PATTERN,
                         GENERIC_CONTINUATION_PATTERN, GENERIC_KV_LEVEL_PATTERN,
                         GENERIC_KV_MESSAGE_PATTERN, GENERIC_LEADING_TIMESTAMP_PATTERN,
                         extract_block_id, extract_generic_fields, build_miner,
                         build_ephemeral_miner)
from src.explain import explain_session
from src.diagnose import (diagnose, SSH_CAUSE_PATTERNS, diagnose_generic,
                           GENERIC_LEVEL_WEIGHT, GENERIC_LEVEL_SEVERITY)
from src.narrate import narrate, narrate_generic, get_cause_info

HDFS_LINE_EXAMPLE = (
    '081109 203607 169 INFO dfs.DataNode$DataXceiver: Receiving block '
    'blk_-4542486744283261479 src: /10.251.30.179:33720 dest: /10.251.30.179:50010'
)

BGL_LINE_EXAMPLE = (
    '- 1117838570 2005.06.03 R02-M1-N0-C:J12-U11 2005-06-03-15.42.50.675872 '
    'R02-M1-N0-C:J12-U11 RAS KERNEL INFO instruction cache parity error corrected'
)

SSH_LINE_EXAMPLE = (
    'Dec 10 06:55:46 LabSZ sshd[24200]: Failed password for invalid user '
    'webmaster from 173.234.31.186 port 38926 ssh2'
)

GENERIC_LINE_EXAMPLE = (
    '2026-08-22 14:05:12 ERROR [http-nio-8080-exec-4] com.example.UserService '
    '- Failed to load user requestId=req-1234'
)

FORMAT_GUESSES = {
    'apache': re.compile(
        r'^\S+ \S+ \S+ \[.*?\] "\S+ \S+ \S+" \d{3} \S+'),
    'hdfs': HDFS_PATTERN,
    'bgl': BGL_PATTERN,
    'ssh': SSH_PATTERN,
    'generic': GENERIC_PATTERN,
    'syslog': re.compile(
        r'^\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2}\s+\S+\s+\S+:'),
    'json_lines': re.compile(r'^\s*\{.*\}\s*$'),
}

SKIPPED_RATIO_WARNING = 0.2
UNKNOWN_EVENT_RATIO_WARNING = 0.3
SAMPLE_LINE_COUNT = 3
SEVERITY_RANK = {'CRITICAL': 4, 'HIGH': 3, 'MEDIUM': 2, 'LOW': 1}


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
                f"by the trained model. Results may be less accurate.")

        message = ('Analysis completed successfully. No anomalous sessions '
                    'were found in this file.' if not anomalies else
                    f'Analysis completed successfully. {len(anomalies)} '
                    f'anomalous session(s) found out of {len(keys)}.')

        risk_level = None
        if anomalies:
            risk_level = max((a['severity'] for a in anomalies),
                              key=lambda s: SEVERITY_RANK.get(s, 0))

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
            'risk_level': risk_level,
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


class WindowedGroupingMixin:
    """Shared by log types with no natural session ID (BGL, SSH): records
    are grouped into fixed-size tumbling windows instead, matching how
    their models were trained."""

    WINDOW_SIZE = 100

    def group_units(self, records):
        windows = {}
        for i, record in enumerate(records):
            key = i // self.WINDOW_SIZE
            windows.setdefault(key, []).append(record)
        return windows

    def format_unit_id(self, key):
        return f'window-{key}'


class BGLDetectionPipeline(WindowedGroupingMixin, BaseDetectionPipeline):
    """BGL: no natural session ID, so records are grouped into fixed-size
    tumbling windows (matching how the models were trained). Cause diagnosis
    uses a classifier trained on real per-line fault-category labels,
    instead of keyword rules."""

    LOG_TYPE = 'bgl'
    LINE_EXAMPLE = BGL_LINE_EXAMPLE

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


class SSHDetectionPipeline(WindowedGroupingMixin, BaseDetectionPipeline):
    """SSH (OpenSSH auth log): no natural session ID -- a connection's PID
    gets reused constantly over a busy multi-week log and its lines
    frequently interleave with other connections in the file, so (unlike
    HDFS's BlockId) PID can't be used as a clean session key. Grouped into
    fixed-size tumbling windows instead, same as BGL. This dataset has no
    ground-truth anomaly labels, so cause diagnosis is keyword-rule-based
    (like HDFS), using patterns grounded in this log's real vocabulary."""

    LOG_TYPE = 'ssh'
    LINE_EXAMPLE = SSH_LINE_EXAMPLE

    def __init__(self, models_dir='models/ssh', config_path='drain3_ssh.ini',
                 drain_state_path='models/ssh_drain_state_full.bin'):
        super().__init__(models_dir, config_path, drain_state_path)

    def parse(self, text):
        records, skipped, sample_skipped = [], 0, []
        for line in text.splitlines():
            stripped = line.strip()
            match = SSH_PATTERN.match(stripped)
            if not match:
                skipped += 1
                if stripped and len(sample_skipped) < SAMPLE_LINE_COUNT:
                    sample_skipped.append(stripped[:200])
                continue
            records.append(match.groupdict())
        return records, skipped, sample_skipped

    def diagnose_cause(self, explanation, unit_records, volume_ratio):
        return diagnose(explanation, self.templates, volume_ratio=volume_ratio,
                         patterns=SSH_CAUSE_PATTERNS, missing_cause='ACTIVITY_SHIFT')


class GenericDetectionPipeline(WindowedGroupingMixin, BaseDetectionPipeline):
    """Generic/Application logs: any application can log any vocabulary, so
    (unlike HDFS/BGL/SSH) there is no fixed real-world dataset to pretrain
    PCA/Isolation Forest/LOF models on ahead of time. Instead of loading
    pretrained artefacts, this pipeline mines Drain3 templates fresh from
    each uploaded file (state discarded after the request) and flags
    windows by log level and keyword rules rather than a trained anomaly
    score -- deliberately simpler and more predictable than the other
    three pipelines, because there's nothing to statistically compare an
    arbitrary application's logs against.
    """

    LOG_TYPE = 'generic'
    LINE_EXAMPLE = GENERIC_LINE_EXAMPLE
    # Smaller than BGL/SSH's 100 deliberately: most uploaded application
    # logs are far shorter than those two datasets, and a 50-100 line
    # window meant a typical few-hundred-line file only had 1-4 windows
    # total -- too few for the relative "is this window unusual for THIS
    # file" comparison in analyze() to have anything meaningful to compare
    # against, so the anomaly rate could only ever land on a handful of
    # coarse values (0%, 50%, 100%...). A smaller window gives moderate-
    # sized files enough windows for that comparison to actually work.
    WINDOW_SIZE = 20

    def __init__(self, config_path='drain3_generic.ini'):
        self.config_path = config_path
        self.templates = {}
        # No pretrained vocabulary/models exist for this log type -- these
        # mirror the shape the other pipelines expose (for /api/health and
        # /api/templates) without claiming a fixed event vocabulary.
        self.event_names = []
        self.models = {'rule_based': None}

    def parse(self, text):
        records, skipped, sample_skipped = [], 0, []
        pending = None
        for raw_line in text.splitlines():
            line = raw_line.rstrip('\r\n')
            if not line.strip():
                continue

            match = GENERIC_PATTERN.match(line)
            kv_match = None if (match and match.group('level')) else GENERIC_KV_LEVEL_PATTERN.search(line)

            if match and match.group('level'):
                if pending:
                    records.append(pending)
                fields = match.groupdict()
                content = fields['content'].strip() or line.strip()
                pending = {
                    'timestamp': fields['timestamp'],
                    'level': fields['level'].upper(),
                    'thread': fields['thread'],
                    'logger': fields['logger'],
                    'content': content,
                    'raw': line.strip(),
                }
                pending.update(extract_generic_fields(content))
            elif kv_match:
                # logfmt-style line ("level=INFO key=value ... message=\"...\"")
                # -- the level is a key=value pair, not a bare token.
                if pending:
                    records.append(pending)
                ts_match = GENERIC_LEADING_TIMESTAMP_PATTERN.match(line)
                msg_match = GENERIC_KV_MESSAGE_PATTERN.search(line)
                pending = {
                    'timestamp': ts_match.group('timestamp') if ts_match else None,
                    'level': kv_match.group('level').upper(),
                    'thread': None,
                    'logger': None,
                    'content': msg_match.group(1) if msg_match else line.strip(),
                    'raw': line.strip(),
                }
                pending.update(extract_generic_fields(line))
            elif pending and GENERIC_CONTINUATION_PATTERN.match(line):
                # A stack-trace line ("at ...", "Caused by: ...") belongs to
                # the log line above it, not to a level/timestamp of its own.
                pending['content'] += ' ' + line.strip()
                pending['raw'] += '\n' + line
            else:
                skipped += 1
                if line.strip() and len(sample_skipped) < SAMPLE_LINE_COUNT:
                    sample_skipped.append(line.strip()[:200])

        if pending:
            records.append(pending)
        return records, skipped, sample_skipped

    def analyze(self, text, model_name='rule_based'):
        records, skipped, sample_skipped = self.parse(text)
        if not records:
            guessed = guess_format(sample_skipped)
            message = ('No lines looked like a recognisable application log. '
                       'A log level such as INFO, WARN or ERROR was expected.')
            if guessed and guessed != self.LOG_TYPE:
                message = (f"This looks like a {guessed.replace('_', ' ')} log, "
                            f"not a general application log this endpoint could parse.")
            return {'error': message,
                    'skipped_lines': skipped,
                    'sample_lines': sample_skipped,
                    'guessed_format': guessed}

        miner = build_ephemeral_miner(self.config_path)
        self.templates = {}
        for record in records:
            result = miner.add_log_message(record['content'])
            record['EventId'] = result['cluster_id']
            self.templates[result['cluster_id']] = result['template_mined']

        units = self.group_units(records)
        keys = list(units)

        # A window is flagged if its severity-weighted suspicious content
        # (FATAL/CRITICAL=3, ERROR=2, WARN=1 per line -- the same weights
        # used for scoring below) is notably above what's typical for the
        # REST of this file. Flagging on "contains any WARN+ line" sounds
        # reasonable but isn't: a healthy service logging occasional
        # retries/slow-query warnings at even a low background rate (a
        # handful of percent of lines) will statistically put at least one
        # such line in nearly every 50-line window, so almost the whole
        # file gets flagged and every analysis reports ~100% anomaly rate
        # regardless of whether anything is actually wrong. Comparing each
        # window against the file's own average -- the same "is this
        # different from normal for this file" idea HDFS/BGL/SSH get from a
        # trained baseline, computed live since there's no pretrained
        # baseline for arbitrary application logs -- fixes that.
        #
        # That comparison breaks down for small files though: with one or
        # two windows total, a window's own score IS the file's average, so
        # it can never register as "above average" no matter how bad it is.
        # There, fall back to an absolute bar instead.
        ABSOLUTE_FLOOR = 3  # e.g. one ERROR + one WARN, or three WARNs
        MIN_WINDOWS_FOR_BASELINE = 4
        window_scores = {}
        has_fatal = {}
        for key in keys:
            levels = [(r.get('level') or '').upper() for r in units[key]]
            window_scores[key] = sum(GENERIC_LEVEL_WEIGHT.get(lvl, 0) for lvl in levels)
            has_fatal[key] = any(lvl in ('FATAL', 'CRITICAL') for lvl in levels)

        if len(keys) >= MIN_WINDOWS_FOR_BASELINE:
            mean_score = sum(window_scores.values()) / len(keys)
            elevated_threshold = max(mean_score * 2, mean_score + ABSOLUTE_FLOOR)
        else:
            elevated_threshold = ABSOLUTE_FLOOR - 1  # i.e. just the absolute floor

        # Pass 1: diagnose every flagged window (fast, no network calls).
        # A FATAL/CRITICAL line always flags its window unconditionally --
        # that severity is significant on its own regardless of how it
        # compares to the rest of the file (a single out-of-memory crash
        # matters even in a file that otherwise has several of them).
        flagged = []
        for key in keys:
            if not (has_fatal[key] or window_scores[key] > elevated_threshold):
                continue

            unit_records = units[key]
            diagnosis = diagnose_generic(unit_records)
            unit_id = self.format_unit_id(key)
            cause_info = get_cause_info(diagnosis['primary_cause'])
            levels_seen = [(r.get('level') or '').upper() for r in unit_records]
            severity = max(
                (GENERIC_LEVEL_SEVERITY[lvl] for lvl in levels_seen if lvl in GENERIC_LEVEL_SEVERITY),
                key=lambda s: SEVERITY_RANK.get(s, 0), default=cause_info['severity'])
            flagged.append({
                'unit_id': unit_id, 'diagnosis': diagnosis, 'cause_info': cause_info,
                'severity': severity, 'score': window_scores[key], 'event_count': len(unit_records),
            })

        flagged.sort(key=lambda f: -f['score'])

        # AI enhancement (explain_evidence_for_anomalies) deliberately does
        # NOT run here. Checking a file is expected to be fast (HDFS/BGL/SSH
        # analyse in well under a second even with 100+ anomalies) -- an
        # external, rate-limited API call has no place in that path. Even
        # capped and run concurrently, it added ~10s+ per upload and, on the
        # free tier's ~20-requests/day quota, started failing outright under
        # any real use. The keyword-based explanation from diagnose_generic
        # is already specific to each line's actual wording; AI enhancement
        # stays available in src/ai_explain.py for a future on-demand path
        # (e.g. an explicit "get a more detailed explanation" action on a
        # single issue) rather than being forced on every analysis.

        anomalies = []
        cause_counts = Counter()
        for f in flagged:
            diagnosis = f['diagnosis']
            cause_counts[diagnosis['primary_cause']] += 1
            anomalies.append({
                'session_id': f['unit_id'],
                'score': round(float(f['score']), 2),
                'event_count': f['event_count'],
                'primary_cause': diagnosis['primary_cause'],
                'title': f['cause_info']['title'],
                'severity': f['severity'],
                'all_causes': diagnosis['all_causes'],
                'report': narrate_generic(diagnosis, f['unit_id'], f['severity']),
                'excess': [],
                'missing': [],
            })

        total_lines = len(records) + skipped
        warnings = []
        skipped_ratio = skipped / total_lines if total_lines else 0
        if skipped_ratio > SKIPPED_RATIO_WARNING:
            warnings.append(
                f"{round(skipped_ratio * 100)}% of lines did not look like "
                f"recognisable log lines and were skipped.")

        message = ('Analysis completed successfully. No anomalous sections '
                    'were found in this file.' if not anomalies else
                    f'Analysis completed successfully. {len(anomalies)} '
                    f'anomalous section(s) found out of {len(keys)}.')

        risk_level = None
        if anomalies:
            risk_level = max((a['severity'] for a in anomalies),
                              key=lambda s: SEVERITY_RANK.get(s, 0))

        return {
            'log_type': self.LOG_TYPE,
            'model': 'rule_based',
            'message': message,
            'total_lines': len(records),
            'skipped_lines': skipped,
            'unknown_events': 0,
            'total_sessions': len(keys),
            'anomalies_found': len(anomalies),
            'anomaly_rate': round(len(anomalies) / len(keys) * 100, 2) if keys else 0,
            'risk_level': risk_level,
            'cause_distribution': dict(cause_counts),
            'warnings': warnings,
            'anomalies': anomalies,
        }


PIPELINE_CLASSES = {
    'hdfs': HDFSDetectionPipeline,
    'bgl': BGLDetectionPipeline,
    'ssh': SSHDetectionPipeline,
    'generic': GenericDetectionPipeline,
}

DetectionPipeline = HDFSDetectionPipeline
