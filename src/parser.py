import re
import pandas as pd
from drain3 import TemplateMiner
from drain3.template_miner_config import TemplateMinerConfig
from drain3.file_persistence import FilePersistence

HDFS_PATTERN = re.compile(
    r'^(?P<date>\d{6})\s+(?P<time>\d{6})\s+(?P<pid>\d+)\s+'
    r'(?P<level>\w+)\s+(?P<component>\S+):\s+(?P<content>.*)$'
)

BGL_PATTERN = re.compile(
    r'^(?P<label>\S+)\s+(?P<timestamp>\d+)\s+(?P<date>\d{4}\.\d{2}\.\d{2})\s+'
    r'(?P<node>\S+)\s+(?P<time>\S+)\s+(?P<noderepeat>\S+)\s+(?P<type>\S+)\s+'
    r'(?P<component>\S+)\s+(?P<level>\S+)\s*(?P<content>.*)$'
)

SSH_PATTERN = re.compile(
    r'^(?P<month>\w{3})\s+(?P<day>\d{1,2})\s+(?P<time>\d{2}:\d{2}:\d{2})\s+'
    r'(?P<host>\S+)\s+(?P<component>\w+)\[(?P<pid>\d+)\]:\s*(?P<content>.*)$'
)

# Generic / Application logs: unlike HDFS/BGL/SSH there is no single fixed
# layout -- this covers common structured application-log shapes (plain
# "<timestamp> LEVEL message", and Spring-Boot-style
# "<timestamp> LEVEL [thread] logger - message"), tolerantly. Only the log
# level is required; timestamp, thread and logger are all optional so a
# file doesn't need every field on every line to be recognised.
GENERIC_LEVELS = 'TRACE|DEBUG|INFO|WARN|WARNING|ERROR|FATAL|CRITICAL'

GENERIC_TIMESTAMP = (
    r'\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?'
)

GENERIC_PATTERN = re.compile(
    rf'^\s*(?:(?P<timestamp>{GENERIC_TIMESTAMP})\s+)?'
    rf'\[?\b(?P<level>{GENERIC_LEVELS})\b\]?\s*[:\-]?\s*'
    rf'(?:\[(?P<thread>[^\]]+)\]\s*)?'
    rf'(?:(?P<logger>[\w$.]+)\s*-\s*)?'
    rf'(?P<content>.*)$'
)

# Stack-trace / multi-line continuation: no level of its own, so it can't
# be matched by GENERIC_PATTERN, but it belongs to the log line above it
# rather than being unrecognised noise.
GENERIC_CONTINUATION_PATTERN = re.compile(
    r'^\s*(at\s+\S+|Caused by:|\.\.\.\s*\d+\s+more|\s{2,}\S)'
)

# logfmt-style structured logs (Go/Zap/logrus-ish): the level is a
# key=value pair rather than a bare token, e.g.
# 'level=INFO server=web-01 ... message="Home page loaded successfully"'.
# GENERIC_PATTERN doesn't match these (its level has to be a bare word near
# the start of the line), so this is tried as a fallback.
GENERIC_KV_LEVEL_PATTERN = re.compile(
    rf'\b(?:level|lvl)\s*=\s*"?(?P<level>{GENERIC_LEVELS})"?\b', re.I)
GENERIC_KV_MESSAGE_PATTERN = re.compile(r'\b(?:message|msg)\s*=\s*"([^"]*)"', re.I)
GENERIC_LEADING_TIMESTAMP_PATTERN = re.compile(rf'^\s*(?P<timestamp>{GENERIC_TIMESTAMP})')

GENERIC_FIELD_PATTERNS = {
    'requestId': re.compile(r'request[_-]?id[=:]\s*"?([^\s",}]+)"?', re.I),
    'status_code': re.compile(r'status(?:_?code)?[=:]\s*"?(\d{3})"?', re.I),
    'duration': re.compile(r'duration[=:]\s*"?(\d+(?:\.\d+)?\s*(?:ms|s|m|h)?)"?', re.I),
}


def extract_generic_fields(content):
    """Best-effort extraction of common structured fields embedded in a
    generic log message (requestId=..., status=200, duration=120ms).
    Returns only the fields actually found -- absence is not an error."""
    found = {}
    for name, pattern in GENERIC_FIELD_PATTERNS.items():
        match = pattern.search(content)
        if match:
            found[name] = match.group(1)
    return found

def parse_fields(path, limit=None):
    rows, skipped = [], 0
    with open(path, errors='ignore') as f:
        for i, line in enumerate(f):
            if limit and i >= limit:
                break
            match = HDFS_PATTERN.match(line.strip())
            if match:
                rows.append(match.groupdict())
            else:
                skipped += 1
    print(f"Parsed: {len(rows)} | Skipped: {skipped}")
    return pd.DataFrame(rows)


def parse_bgl_fields(path, limit=None):
    rows, skipped = [], 0
    with open(path, errors='ignore') as f:
        for i, line in enumerate(f):
            if limit and i >= limit:
                break
            match = BGL_PATTERN.match(line.strip())
            if match:
                rows.append(match.groupdict())
            else:
                skipped += 1
    print(f"Parsed: {len(rows)} | Skipped: {skipped}")
    return pd.DataFrame(rows)

def parse_ssh_fields(path, limit=None):
    rows, skipped = [], 0
    with open(path, errors='ignore') as f:
        for i, line in enumerate(f):
            if limit and i >= limit:
                break
            match = SSH_PATTERN.match(line.strip())
            if match:
                rows.append(match.groupdict())
            else:
                skipped += 1
    print(f"Parsed: {len(rows)} | Skipped: {skipped}")
    return pd.DataFrame(rows)


def extract_block_id(content):
    match = re.search(r'(blk_-?\d+)', str(content))
    return match.group(1) if match else None


def to_timestamp(df):
    return pd.to_datetime(df['date'] + df['time'], format='%y%m%d%H%M%S')


def build_miner(config_path='../drain3.ini', state_path='../models/drain_state.bin'):
    config = TemplateMinerConfig()
    config.load(config_path)
    config.profiling_enabled = False
    persistence = FilePersistence(state_path)
    return TemplateMiner(persistence, config=config)


def build_ephemeral_miner(config_path='drain3_generic.ini'):
    """A Drain3 miner with no persisted state -- used for Generic/Application
    logs, where there's no fixed vocabulary to pretrain on ahead of time.
    Templates are mined fresh from each uploaded file and discarded after
    the request, instead of being loaded from (and saved back to) disk."""
    config = TemplateMinerConfig()
    config.load(config_path)
    config.profiling_enabled = False
    return TemplateMiner(config=config)

def mine_templates(df, miner):
    event_ids, templates = [], []
    for content in df['content']:
        result = miner.add_log_message(str(content))
        event_ids.append(result['cluster_id'])
        templates.append(result['template_mined'])
    df['EventId'] = event_ids
    df['EventTemplate'] = templates
    return df