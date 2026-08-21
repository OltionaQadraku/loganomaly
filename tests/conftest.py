import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.db import Base, get_db
import api.db_models  

TEST_DB_PATH = 'test_logsense.db'
if os.path.exists(TEST_DB_PATH):
    os.remove(TEST_DB_PATH)

test_engine = create_engine(f'sqlite:///./{TEST_DB_PATH}', connect_args={'check_same_thread': False})
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
Base.metadata.create_all(bind=test_engine)


def _override_get_db():
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


from api.main import app  
from api.pipeline import DetectionPipeline, BGLDetectionPipeline  

app.dependency_overrides[get_db] = _override_get_db

VALID_HDFS_LINES = [
    '081109 203607 169 INFO dfs.DataNode$DataXceiver: Receiving block '
    'blk_-4542486744283261479 src: /10.251.30.179:33720 dest: /10.251.30.179:50010',
    '081109 203607 174 INFO dfs.DataNode$DataXceiver: Receiving block '
    'blk_-4542486744283261479 src: /10.251.30.179:47345 dest: /10.251.30.179:50010',
    '081109 203607 33 INFO dfs.FSNamesystem: BLOCK* NameSystem.allocateBlock: '
    '/user/root/rand/_temporary/_task_200811092030_0001_m_000018_0/part-00018. '
    'blk_-4542486744283261479',
]

VALID_BGL_LINES = [
    '- 1117838570 2005.06.03 R02-M1-N0-C:J12-U11 2005-06-03-15.42.50.675872 '
    'R02-M1-N0-C:J12-U11 RAS KERNEL INFO instruction cache parity error corrected',
    '- 1117838573 2005.06.03 R02-M1-N0-C:J12-U11 2005-06-03-15.42.53.276129 '
    'R02-M1-N0-C:J12-U11 RAS KERNEL INFO instruction cache parity error corrected',
    'KERNRTSP 1121115817 2005.07.11 R01-M0-N1-C:J09-U11 2005-07-11-14.03.37.675251 '
    'R01-M0-N1-C:J09-U11 RAS KERNEL FATAL rts panic! - stopping execution',
]


@pytest.fixture(scope='session')
def pipeline():
    return DetectionPipeline()


@pytest.fixture(scope='session')
def bgl_pipeline():
    return BGLDetectionPipeline()


@pytest.fixture(scope='session')
def client():
    """A TestClient logged in as a fresh test user (cookies persist across
    requests made with this client, same as a real browser session)."""
    c = TestClient(app)
    c.post('/api/register', json={'username': 'testuser', 'password': 'testpass123'})
    return c


@pytest.fixture
def valid_hdfs_text():
    return '\n'.join(VALID_HDFS_LINES)


@pytest.fixture
def valid_bgl_text():
    return '\n'.join(VALID_BGL_LINES)
