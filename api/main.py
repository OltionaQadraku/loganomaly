import logging
import os
import time
from collections import Counter

from fastapi import Depends, FastAPI, File, HTTPException, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session

from api.auth import COOKIE_NAME, create_token, get_current_user, hash_password, verify_password
from api.db import get_db, init_db
from api.db_models import Run, User
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

init_db()


def log_failure(reason):
    failure_counts[reason] += 1
    logger.warning('upload rejected: %s', reason)


MAX_FILE_SIZE = 20 * 1024 * 1024  
MIN_PASSWORD_LENGTH = 6
MIN_USERNAME_LENGTH = 3
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


class Credentials(BaseModel):
    username: str
    password: str


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
    allow_credentials=True,
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


def set_auth_cookie(response, user_id):
    response.set_cookie(
        COOKIE_NAME, create_token(user_id),
        httponly=True, samesite='lax', max_age=60 * 60 * 24 * 7,
    )


@app.post("/api/register")
def register(payload: Credentials, response: Response, db: Session = Depends(get_db)):
    username = payload.username.strip()
    if len(username) < MIN_USERNAME_LENGTH:
        raise HTTPException(400, {
            'reason': 'INVALID_USERNAME',
            'message': f"Username must be at least {MIN_USERNAME_LENGTH} characters.",
        })
    if len(payload.password) < MIN_PASSWORD_LENGTH:
        raise HTTPException(400, {
            'reason': 'WEAK_PASSWORD',
            'message': f"Password must be at least {MIN_PASSWORD_LENGTH} characters.",
        })
    if db.query(User).filter(User.username == username).first():
        raise HTTPException(400, {
            'reason': 'USERNAME_TAKEN',
            'message': "That username is already taken.",
        })

    user = User(username=username, password_hash=hash_password(payload.password))
    db.add(user)
    db.commit()
    db.refresh(user)

    set_auth_cookie(response, user.id)
    return {"username": user.username}


@app.post("/api/login")
def login(payload: Credentials, response: Response, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == payload.username.strip()).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(401, {
            'reason': 'INVALID_CREDENTIALS',
            'message': "Incorrect username or password.",
        })

    set_auth_cookie(response, user.id)
    return {"username": user.username}


@app.post("/api/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE_NAME)
    return {"ok": True}


@app.get("/api/me")
def me(user: User = Depends(get_current_user)):
    return {"username": user.username}


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
def stats(db: Session = Depends(get_db)):
    return {
        "total_runs": db.query(Run).count(),
        "upload_failures": dict(failure_counts),
    }


@app.post("/api/analyze")
async def analyze(file: UploadFile = File(...), model: str = "pca", top: int = 20,
                   log_type: str = "auto", user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
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
    started_at = time.time()
    result = pipeline.analyze(content, model)
    result_duration = round(time.time() - started_at, 2)

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

    run = Run(
        user_id=user.id,
        filename=file.filename,
        log_type=result.get('log_type'),
        model=model,
        message=result.get('message'),
        total_lines=result.get('total_lines'),
        skipped_lines=result.get('skipped_lines'),
        unknown_events=result.get('unknown_events'),
        total_sessions=result.get('total_sessions'),
        anomalies_found=result.get('anomalies_found'),
        anomaly_rate=result.get('anomaly_rate'),
        risk_level=result.get('risk_level'),
        duration_seconds=result_duration,
        cause_distribution=result.get('cause_distribution'),
        warnings=result.get('warnings', []),
        anomalies=result.get('anomalies', []),
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    full = run.to_dict()
    return {**{k: v for k, v in full.items() if k != "anomalies"},
            "anomalies": [
                {k: a[k] for k in ('session_id', 'score', 'event_count',
                                   'primary_cause', 'title', 'severity')}
                for a in full["anomalies"][:top]
            ]}


def get_owned_run(run_id, user, db):
    run = db.query(Run).filter(Run.id == run_id, Run.user_id == user.id).first()
    if not run:
        raise HTTPException(404, "Run not found")
    return run


@app.get("/api/runs/{run_id}/anomalies")
def list_anomalies(run_id: str, skip: int = 0, limit: int = 50, cause: str = None,
                    user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    run = get_owned_run(run_id, user, db)

    items = run.anomalies
    if cause:
        items = [a for a in items if a["primary_cause"] == cause]

    return {
        "total": len(items),
        "items": [{k: a[k] for k in ('session_id', 'score', 'event_count',
                                     'primary_cause', 'title', 'severity')}
                  for a in items[skip:skip + limit]],
    }


@app.get("/api/runs/{run_id}/anomalies/{session_id}")
def get_anomaly(run_id: str, session_id: str,
                 user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    run = get_owned_run(run_id, user, db)

    for item in run.anomalies:
        if item["session_id"] == session_id:
            return item

    raise HTTPException(404, "Session not found")


@app.get("/api/runs")
def list_runs(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    runs = (db.query(Run)
              .filter(Run.user_id == user.id)
              .order_by(Run.analyzed_at.desc())
              .all())
    return [r.to_dict(include_anomalies=False) for r in runs]


@app.get("/api/runs/{run_id}")
def get_run(run_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return get_owned_run(run_id, user, db).to_dict()


@app.get("/api/templates")
def templates(log_type: str = "hdfs"):
    return require_pipeline(log_type).templates
