# LogSense

Detecting and explaining anomalies in log files using machine learning.

## Overview

LogSense is a web application that accepts raw log files, parses them automatically, and detects anomalous sessions using unsupervised machine learning. It also identifies which log events caused a session to be
flagged so the output is an explanation, not just an alert.

Unlike rule-based monitoring, it learns normal behaviour from the data and requires no predefined rules.

## Algorithms

Isolation Forest, Local Outlier, Factor, PCA, Random Forest (baseline)

## Tech Stack

Python, scikit-learn, Drain3, FastAPI, React and PostgreSQL

## Installation

```bash
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Configuration

Optional environment variables:

- `LOGSENSE_SECRET_KEY` -- secret used to sign login sessions. Falls back to
  a development-only default if unset; set a real value in production.
- `GEMINI_API_KEY` -- if set, the Generic/Application log pipeline uses the
  Gemini API (free tier at [aistudio.google.com](https://aistudio.google.com/apikey))
  to write a more specific, plain-language explanation for each flagged log
  line (naming the actual service/resource involved where the line mentions
  one), instead of only the built-in keyword-rule explanations. Entirely
  optional -- without it, Generic/Application analysis still works exactly
  as before, using the keyword rules alone.

## Dataset

HDFS dataset from [LogHub](https://github.com/logpai/loghub).

