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

def mine_templates(df, miner):
    event_ids, templates = [], []
    for content in df['content']:
        result = miner.add_log_message(str(content))
        event_ids.append(result['cluster_id'])
        templates.append(result['template_mined'])
    df['EventId'] = event_ids
    df['EventTemplate'] = templates
    return df