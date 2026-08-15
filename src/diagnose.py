import re

CAUSE_PATTERNS = {
    'OVERLOAD': [
        r'timeout', r'timed out', r'retry', r'retrying', r'queue.*full',
        r'pool.*exhaust', r'too many', r'rate limit', r'throttl', r'backlog',
        r'slow', r'congestion',
    ],
    'COMPONENT_FAILURE': [
        r'connection refused', r'unreachable', r'no route', r'disconnect',
        r'not responding', r'unavailable', r'down', r'lost',
        r'failed to connect', r'broken pipe',
    ],
    'APPLICATION_ERROR': [
        r'exception', r'error', r'null', r'invalid', r'parse',
        r'illegal', r'corrupt', r'malformed', r'assert',
    ],
    'SECURITY': [
        r'unauthorized', r'denied', r'forbidden', r'authentication',
        r'failed login', r'invalid token', r'permission',
    ],
    'RESOURCE': [
        r'out of memory', r'no space', r'disk full', r'quota',
        r'insufficient', r'limit exceeded',
    ],
    'DATA_INTEGRITY': [
        r'checksum', r'corrupt', r'crc', r'mismatch',
        r'not found in volumemap', r'does not belong to any file',
        r'already existing',
    ],
    'RECOVERY_ACTION': [
        r'redundant', r'reopen', r'replicate',
        r'pendingreplicationmonitor', r'neededreplications',
    ],
}

INCOMPLETE_THRESHOLD = 0.6


def match_causes(template_text):
    """Return the cause categories a template text matches."""
    text = template_text.lower()
    return [cause for cause, patterns in CAUSE_PATTERNS.items()
            if any(re.search(p, text) for p in patterns)]


def diagnose(explanation, template_map, volume_ratio=1.0):
    """Turn raw excess/missing evidence into ranked likely causes."""
    votes = {}
    evidence = []

    for item in explanation['excess']:
        text = template_map[item['event']]
        for cause in match_causes(text):
            votes[cause] = votes.get(cause, 0) + item['deviation']
            evidence.append(f"{text[:70]} occurred {item['observed']:.0f}x "
                            f"(expected {item['expected']})")
            
    missing_weight = sum(-i['deviation'] for i in explanation['missing'])
    expected_total = sum(i['expected'] for i in explanation['missing'])
    if expected_total and missing_weight / expected_total > INCOMPLETE_THRESHOLD:
        votes['INCOMPLETE_EXECUTION'] = votes.get('INCOMPLETE_EXECUTION', 0) + missing_weight
        for item in explanation['missing'][:3]:
            evidence.append(f"{template_map[item['event']][:70]} missing "
                            f"(expected {item['expected']})")

    if volume_ratio > 2.0:
        votes['OVERLOAD'] = votes.get('OVERLOAD', 0) + volume_ratio
        evidence.append(f"Log volume {volume_ratio:.1f}x above the normal average")

    ranked = sorted(votes.items(), key=lambda kv: -kv[1])
    return {
        'primary_cause': ranked[0][0] if ranked else 'UNKNOWN',
        'all_causes': [c for c, _ in ranked],
        'evidence': evidence,
    }