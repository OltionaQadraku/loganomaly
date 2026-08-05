"""Build a demo log file containing only complete block lifecycles."""
import re
import pandas as pd

BLOCK_RE = re.compile(r'(blk_-?\d+)')

labels = pd.read_csv('data/raw/anomaly_label.csv')
normal = labels[labels.Label == 'Normal'].BlockId.sample(400, random_state=42)
anomaly = labels[labels.Label == 'Anomaly'].BlockId.sample(100, random_state=42)
wanted = set(normal) | set(anomaly)

kept = 0
with open('data/raw/HDFS.log', errors='ignore') as fi, \
     open('data/raw/demo.log', 'w') as fo:
    for line in fi:
        match = BLOCK_RE.search(line)
        if match and match.group(1) in wanted:
            fo.write(line)
            kept += 1

print(f"Wrote {kept} lines for {len(wanted)} complete sessions")
labels[labels.BlockId.isin(wanted)].to_csv('data/raw/demo_labels.csv', index=False)