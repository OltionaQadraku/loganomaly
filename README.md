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

## Dataset

HDFS dataset from [LogHub](https://github.com/logpai/loghub).

