import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger('logsense')

MODEL = 'openai/gpt-oss-20b'
MAX_LINES_PER_CALL = 5
TIMEOUT_S = 10

_client = None
_client_checked = False

PROMPT_TEMPLATE = (
    "You are helping a non-technical person understand application log "
    "errors. For each numbered log line below, write ONE short (1-2 "
    "sentence) plain-language explanation of what it most likely means in "
    "practice. Ground the explanation in the SPECIFIC wording of that "
    "line -- name the actual service, component or resource it mentions, "
    "if any -- rather than a generic description. Do not speculate beyond "
    "what the line actually says, and avoid technical jargon.\n\n"
    "Respond with ONLY a JSON object mapping each line number (as a "
    "string) to its explanation, and nothing else. Example shape: "
    '{{"0": "...", "1": "..."}}\n\n'
    "{lines}"
)


def _get_client():
    """Lazily build the Groq client from GROQ_API_KEY. Returns None (and
    only logs once) if no key is configured or the SDK isn't installed --
    callers must treat that as "AI enhancement unavailable" and fall back
    to the keyword-based explanations, not as an error."""
    global _client, _client_checked
    if _client_checked:
        return _client
    _client_checked = True

    api_key = os.environ.get('GROQ_API_KEY')
    if not api_key:
        return None
    try:
        from groq import Groq
        _client = Groq(api_key=api_key, max_retries=0, timeout=TIMEOUT_S)
    except Exception as exc:
        logger.warning('Groq client unavailable, using keyword-based '
                        'explanations only: %s', exc)
        _client = None
    return _client


def ai_enabled():
    """Whether AI-enhanced explanations are configured and available."""
    return _get_client() is not None


def explain_evidence_lines(evidence):
    """Ask Groq for a specific, plain-language explanation of each
    evidence line, grounded in its exact wording -- richer than the fixed
    keyword-rule text, since an LLM can pick up on details (a service
    name, a specific resource) a regex can't.

    Returns {index: explanation} for lines it could explain. Returns {}
    (never raises) if no API key is configured or the call fails for any
    reason -- callers keep the keyword-based explanation already computed
    for those lines, so a missing key or a network hiccup never breaks
    analysis, it only means slightly less specific wording.
    """
    client = _get_client()
    if not client or not evidence:
        return {}

    items = evidence[:MAX_LINES_PER_CALL]
    lines_block = '\n'.join(
        f"{i}. [{item['level']}] {item['text']}" for i, item in enumerate(items))
    prompt = PROMPT_TEMPLATE.format(lines=lines_block)

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{'role': 'user', 'content': prompt}],
            response_format={'type': 'json_object'},
        )
        parsed = json.loads(response.choices[0].message.content)
        return {int(k): v for k, v in parsed.items()
                if k.isdigit() and int(k) < len(items) and isinstance(v, str) and v.strip()}
    except Exception as exc:
        logger.warning('AI explanation call failed, falling back to '
                        'keyword-based explanations: %s', exc)
        return {}


def explain_evidence_for_anomalies(evidence_by_anomaly, max_anomalies=5):
    """Enhance evidence for multiple flagged windows at once.

    Calling the AI once per anomaly, sequentially, made analysis of a file
    with several flagged sections take tens of seconds to minutes. Two
    things bound that: only the first `max_anomalies` (callers should pass
    them ranked by severity/score) get AI treatment at all -- the rest keep
    their keyword-based explanation -- and the calls that do happen run
    concurrently instead of one after another, so N calls cost roughly one
    call's worth of wall-clock time, not N.

    `evidence_by_anomaly` is a list of evidence lists (one per anomaly).
    Returns a list of the same length, each entry the {index: explanation}
    dict `explain_evidence_lines` would have returned for that anomaly
    (empty for anomalies beyond `max_anomalies`, or where the call failed).
    """
    results = [{} for _ in evidence_by_anomaly]
    if not ai_enabled():
        return results

    selected = list(enumerate(evidence_by_anomaly))[:max_anomalies]
    if not selected:
        return results

    with ThreadPoolExecutor(max_workers=len(selected)) as pool:
        futures = {pool.submit(explain_evidence_lines, evidence): i for i, evidence in selected}
        for future in futures:
            i = futures[future]
            try:
                results[i] = future.result()
            except Exception as exc:
                logger.warning('AI explanation task failed for anomaly %d: %s', i, exc)

    return results
