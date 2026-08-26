# LogSense

Detecting and explaining anomalies in log files using machine learning.

## What it does

You upload a log file, and instead of just dumping raw lines back at you, LogSense tells you what actually looks wrong with it. It figures out the log type on it, groups the file into sessions or windows depending on the format, and runs unsupervised ML models to flag the ones that don't look like the rest. For every flagged section it also tries to explain why what kind of problem this usually is, what in the log actually pointed to it, and what you should go check.

The whole point was to not build another tool that just says "something's off, good luck." Regular log monitoring means someone sat down and wrote rules for every failure they could think of ahead of time which falls apart the moment something happens that nobody predicted. Here the models just learn what "normal" looks like from the data itself, so they can catch things nobody explicitly told them to look for.

## Log types it handles

**HDFS** was the first one. Hadoop logs happen to include a real block ID right in the text, so grouping lines into sessions is straightforward every line already says which session it belongs to.

**BGL** is a log pulled from an actual IBM Blue Gene/L supercomputer, and it doesn't give you anything like that block ID. There's no clean way to say "these lines belong together," so instead the log just gets cut into fixed-size windows and each window is judged on its own.

**OpenSSH** is mostly a server getting hammered by bots trying random logins. Same deal as BGL no natural grouping, so it's windowed too.

**Generic/Application** covers everything else, and it works differently from the other three. HDFS, BGL, and OpenSSH each have a real dataset behind them that the models were trained on ahead of time .

## Algorithms

**PCA / Isolation Forest / Local Outlier Factor**
The three models that actually do the anomaly detection. They're unsupervised so they're not limited to catching only the failures they've seen labelled examples of before.
**Random Forest**
Only used for BGL, to figure out which of the 32 fault categories a flagged window matches once we already know something's wrong. Not involved in detecting the anomaly itself.
**Drain3** 
Groups similar log lines together, so the same message with a different number or IP in it still counts as one event, not a new one every time.

## Stack

Python / FastAPI on the backend, scikit-learn + Drain3 for the ML side, SQLite for storage, JWT + bcrypt for login, React 19 + Vite on the frontend. PDF export is done client-side with jsPDF. There's an optional integration with Groq for extra-detailed, on-demand explanations on the Generic pipeline, but it's off unless you configure a key. 120 pytest tests cover the backend.

## Getting it running

Backend:

```bash
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
venv\Scripts\python.exe -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

Frontend, in another terminal:

```bash
cd web
npm install
npm run dev
```

Then just open URL Vite prints (usually `http://localhost:5173`).

Run the tests with `pytest` from the project root.

## Environment variables (both optional)

`LOGSENSE_SECRET_KEY`
Signs the login sessions. There's a dev fallback so you don't need this just to try the app.

`GROQ_API_KEY`
If set, there's a "Get a more detailed explanation" button on each flagged issue in the Generic/Application pipeline that asks Groq for a more specific explanation of that one line. Get a free key at [console.groq.com/keys](https://console.groq.com/keys). Without it, everything still works with the built-in keyword explanations instead. It's on-demand, not called automatically during analysis, so uploads never wait on it. You call it yourself, whenever you want, by clicking that button on a flagged issue.

## Where the data came from

**HDFS**
[LogHub](https://github.com/logpai/loghub), 11,175,629 lines, comes with real anomaly labels.
**BGL**
[Zenodo](https://zenodo.org/records/8196385), 4,747,963 messages from a real Blue Gene/L machine, labelled fault categories.
**OpenSSH** 
Same Zenodo source, 655,146 messages from a real SSH server over 28 days. No labels here, hence the bootstrap approach mentioned above.
**Generic/Application** 
No dataset, analysed live.
