import uuid
from datetime import datetime

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from api.pipeline import DetectionPipeline

app = FastAPI(title="LogSense API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)
@app.get("/")
def root():
    return {"service": "LogSense API", "docs": "/docs"}

pipeline = DetectionPipeline()
runs = {}


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "models": list(pipeline.models),
        "events": len(pipeline.event_names),
    }


@app.post("/api/analyze")
async def analyze(file: UploadFile = File(...), model: str = "pca", top: int = 20):
    if model not in pipeline.models:
        raise HTTPException(400, f"Unknown model: {model}")

    content = (await file.read()).decode("utf-8", errors="ignore")
    result = pipeline.analyze(content, model)

    if "error" in result:
        raise HTTPException(400, result["error"])

    run_id = str(uuid.uuid4())[:8]
    result["run_id"] = run_id
    result["filename"] = file.filename
    result["analyzed_at"] = datetime.utcnow().isoformat()
    runs[run_id] = result

    # Return a light summary; details are fetched per session
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
    return pipeline.templates