import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.pipeline import DetectionPipeline

VALID_HDFS_LINES = [
    '081109 203607 169 INFO dfs.DataNode$DataXceiver: Receiving block '
    'blk_-4542486744283261479 src: /10.251.30.179:33720 dest: /10.251.30.179:50010',
    '081109 203607 174 INFO dfs.DataNode$DataXceiver: Receiving block '
    'blk_-4542486744283261479 src: /10.251.30.179:47345 dest: /10.251.30.179:50010',
    '081109 203607 33 INFO dfs.FSNamesystem: BLOCK* NameSystem.allocateBlock: '
    '/user/root/rand/_temporary/_task_200811092030_0001_m_000018_0/part-00018. '
    'blk_-4542486744283261479',
]


@pytest.fixture(scope='session')
def pipeline():
    return DetectionPipeline()


@pytest.fixture(scope='session')
def client():
    return TestClient(app)


@pytest.fixture
def valid_hdfs_text():
    return '\n'.join(VALID_HDFS_LINES)
