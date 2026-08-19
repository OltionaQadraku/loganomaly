import logging
import os
import uuid
from collections import Counter
from datetime import datetime

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from api.pipeline import PIPELINE_CLASSES, HDFS_LINE_EXAMPLE, BGL_LINE_EXAMPLE

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

FORMAT_INFO = {
    'hdfs': {
        "supported_format": "HDFS",
        "line_pattern": "<date> <time> <pid> <level> <component>: <message>",
        "example_line": HDFS_LINE_EXAMPLE,
        "notes": "Only HDFS-style logs are supported for this log type — the "
                 "pattern above must match each line for it to be understood.",
    },
    'bgl': {
        "supported_format": "BGL",
        "line_pattern": "<label> <timestamp> <date> <node> <time> <node_repeat> "
                         "<type> <component> <level> <message>",
        "example_line": BGL_LINE_EXAMPLE,
        "notes": "Only BGL-style logs are supported for this log type — the "
                 "pattern above must match each line for it to be understood. "
                 "'label' is '-' for normal lines or a fault-category code "
                 "(e.g. KERNDTLB) for known failures.",
    },
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


pipelines = {}
startup_errors = {}
for log_type, pipeline_cls in PIPELINE_CLASSES.items():
    try:
        pipelines[log_type] = pipeline_cls()
    except Exception as exc:
        startup_errors[log_type] = str(exc)
        logger.error('%s model artifacts failed to load: %s', log_type, exc)

runs = {}


def require_pipeline(log_type):
    if log_type not in PIPELINE_CLASSES:
        raise HTTPException(400, {
            'reason': 'UNKNOWN_LOG_TYPE',
            'message': f"Unknown log_type '{log_type}'. Supported: "
                       f"{', '.join(PIPELINE_CLASSES)}.",
        })
    if log_type not in pipelines:
        raise HTTPException(503, {
            'reason': 'MODEL_UNAVAILABLE',
            'message': f"The '{log_type}' analysis models failed to load on "
                       f"the server. Uploads for this log type can't be "
                       f"analysed right now.",
        })
    return pipelines[log_type]


def detect_log_type(content):
    """Best-effort auto-detection: ask every loaded pipeline how much of the
    content it actually understands, and pick the clear winner. Users
    shouldn't need to know or choose a log type up front."""
    best_type, best_ratio = None, 0.0
    for candidate_type, candidate_pipeline in pipelines.items():
        records, skipped, _ = candidate_pipeline.parse(content)
        total = len(records) + skipped
        ratio = (len(records) / total) if total else 0
        if ratio > 0.5 and ratio > best_ratio:
            best_type, best_ratio = candidate_type, ratio
    return best_type


@app.get("/api/health")
def health():
    return {
        "status": "ok" if not startup_errors else "degraded",
        "log_types": {
            log_type: (
                {"status": "ok", "models": list(p.models), "events": len(p.event_names)}
                if (p := pipelines.get(log_type)) is not None
                else {"status": "degraded", "error": startup_errors.get(log_type)}
            )
            for log_type in PIPELINE_CLASSES
        },
    }


@app.get("/api/format-info")
def format_info(log_type: str = "hdfs"):
    if log_type not in FORMAT_INFO:
        raise HTTPException(400, {
            'reason': 'UNKNOWN_LOG_TYPE',
            'message': f"Unknown log_type '{log_type}'. Supported: "
                       f"{', '.join(FORMAT_INFO)}.",
        })
    return FORMAT_INFO[log_type]


@app.get("/api/stats")
def stats():
    return {
        "total_runs": len(runs),
        "upload_failures": dict(failure_counts),
    }


@app.post("/api/analyze")
async def analyze(file: UploadFile = File(...), model: str = "pca", top: int = 20,
                   log_type: str = "auto"):
    if model not in {'pca', 'isolation_forest', 'lof'}:
        raise HTTPException(400, f"Unknown model: {model}")

    raw = await file.read()
    validate_upload(file.filename, raw)

    try:
        content = raw.decode("utf-8")
        encoding_issues = 0
    except UnicodeDecodeError:
        content = raw.decode("utf-8", errors="replace")
        encoding_issues = content.count("�")

    if log_type == "auto":
        log_type = detect_log_type(content) or next(iter(pipelines), 'hdfs')

    pipeline = require_pipeline(log_type)
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
                                   'primary_cause', 'title', 'severity')}
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
                                     'primary_cause', 'title', 'severity')}
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
def templates(log_type: str = "hdfs"):
    return require_pipeline(log_type).templates
