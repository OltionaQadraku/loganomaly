import logging
import os
import uuid
from collections import Counter
from datetime import datetime

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from api.pipeline import DetectionPipeline, HDFS_LINE_EXAMPLE

app = FastAPI(title="LogSense API")

os.makedirs('logs', exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[logging.FileHandler('logs/failures.log'), logging.StreamHandler()],
)
logger = logging.getLogger('logsense')
failure_counts = Counter()


def log_failure(reason):
    failure_counts[reason] += 1
    logger.warning('upload rejected: %s', reason)

MAX_FILE_SIZE = 20 * 1024 * 1024  
BLOCKED_EXTENSIONS = {
    '.zip', '.rar', '.7z', '.gz', '.tar',
    '.png', '.jpg', '.jpeg', '.gif', '.bmp',
    '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
    '.exe', '.dll', '.bin', '.so', '.dylib',
}


def validate_upload(filename, content):
    """Reject obviously-wrong uploads before wasting a parse attempt on them,
    with a message that tells a non-technical user what was actually wrong."""
    ext = os.path.splitext(filename or '')[1].lower()
    if ext in BLOCKED_EXTENSIONS:
        log_failure('UNSUPPORTED_FILE_TYPE')
        raise HTTPException(400, {
            'reason': 'UNSUPPORTED_FILE_TYPE',
            'message': f"'{ext}' files aren't supported. Please upload a "
                       f"plain-text log file (.log or .txt).",
        })

    if len(content) > MAX_FILE_SIZE:
        log_failure('FILE_TOO_LARGE')
        raise HTTPException(400, {
            'reason': 'FILE_TOO_LARGE',
            'message': f"The file is larger than "
                       f"{MAX_FILE_SIZE // (1024 * 1024)} MB. Please upload "
                       f"a smaller log file.",
        })

    if b'\x00' in content:
        log_failure('BINARY_FILE')
        raise HTTPException(400, {
            'reason': 'BINARY_FILE',
            'message': "This file looks like a binary file, not a plain-text "
                       "log file. Please upload a .log or .txt file.",
        })

    if not content.strip():
        log_failure('EMPTY_FILE')
        raise HTTPException(400, {
            'reason': 'EMPTY_FILE',
            'message': "This file is empty.",
        })

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://localhost:\d+",
    allow_methods=["*"],
    allow_headers=["*"],
)
@app.get("/")
def root():
    return {"service": "LogSense API", "docs": "/docs"}

try:
    pipeline = DetectionPipeline()
    startup_error = None
except Exception as exc:
    pipeline = None
    startup_error = str(exc)
    logger.error('model artifacts failed to load: %s', exc)

runs = {}


def require_pipeline():
    if pipeline is None:
        raise HTTPException(503, {
            'reason': 'MODEL_UNAVAILABLE',
            'message': "The analysis models failed to load on the server. "
                       "Uploads can't be analysed right now.",
        })
    return pipeline


@app.get("/api/health")
def health():
    if pipeline is None:
        return {"status": "degraded", "error": startup_error}
    return {
        "status": "ok",
        "models": list(pipeline.models),
        "events": len(pipeline.event_names),
    }


@app.get("/api/format-info")
def format_info():
    return {
        "supported_format": "HDFS",
        "line_pattern": "<date> <time> <pid> <level> <component>: <message>",
        "example_line": HDFS_LINE_EXAMPLE,
        "notes": "Only HDFS-style logs are supported — the pattern above must "
                 "match each line for it to be understood.",
    }


@app.get("/api/stats")
def stats():
    return {
        "total_runs": len(runs),
        "upload_failures": dict(failure_counts),
    }


@app.post("/api/analyze")
async def analyze(file: UploadFile = File(...), model: str = "pca", top: int = 20):
    pipeline = require_pipeline()
    if model not in pipeline.models:
        raise HTTPException(400, f"Unknown model: {model}")

    raw = await file.read()
    validate_upload(file.filename, raw)

    try:
        content = raw.decode("utf-8")
        encoding_issues = 0
    except UnicodeDecodeError:
        content = raw.decode("utf-8", errors="replace")
        encoding_issues = content.count("�")

    result = pipeline.analyze(content, model)

    if "error" in result:
        log_failure('FORMAT_NOT_RECOGNISED')
        raise HTTPException(400, {
            'reason': 'FORMAT_NOT_RECOGNISED',
            'message': result['error'],
            'skipped_lines': result.get('skipped_lines'),
            'sample_lines': result.get('sample_lines'),
            'guessed_format': result.get('guessed_format'),
        })

    if encoding_issues:
        result.setdefault('warnings', []).insert(
            0, f"{encoding_issues} character(s) could not be read as UTF-8 "
               f"and were replaced — the file may use a different encoding.")

    run_id = str(uuid.uuid4())[:8]
    result["run_id"] = run_id
    result["filename"] = file.filename
    result["analyzed_at"] = datetime.utcnow().isoformat()
    runs[run_id] = result

    return {**{k: v for k, v in result.items() if k != "anomalies"},
            "anomalies": [
                {k: a[k] for k in ('session_id', 'score', 'event_count',
                                   'primary_cause')}
                for a in result["anomalies"][:top]
            ]}


@app.get("/api/runs/{run_id}/anomalies")
def list_anomalies(run_id: str, skip: int = 0, limit: int = 50, cause: str = None):
    if run_id not in runs:
        raise HTTPException(404, "Run not found")

    items = runs[run_id]["anomalies"]
    if cause:
        items = [a for a in items if a["primary_cause"] == cause]

    return {
        "total": len(items),
        "items": [{k: a[k] for k in ('session_id', 'score', 'event_count',
                                     'primary_cause')}
                  for a in items[skip:skip + limit]],
    }


@app.get("/api/runs/{run_id}/anomalies/{session_id}")
def get_anomaly(run_id: str, session_id: str):
    if run_id not in runs:
        raise HTTPException(404, "Run not found")

    for item in runs[run_id]["anomalies"]:
        if item["session_id"] == session_id:
            return item

    raise HTTPException(404, "Session not found")

@app.get("/api/runs")
def list_runs():
    return [{k: v for k, v in run.items() if k != "anomalies"}
            for run in runs.values()]


@app.get("/api/runs/{run_id}")
def get_run(run_id: str):
    if run_id not in runs:
        raise HTTPException(404, "Run not found")
    return runs[run_id]


@app.get("/api/templates")
def templates():
    return require_pipeline().templates