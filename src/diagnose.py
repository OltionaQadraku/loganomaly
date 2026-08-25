import re
from collections import Counter

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

# Grounded in the real Drain3 templates mined from the loghub OpenSSH
# dataset (data/parsed/ssh_parsed_full.csv) -- this log's vocabulary is
# dominated by brute-force login attempts, so its keyword rules differ
# from HDFS's storage-service vocabulary above.
SSH_CAUSE_PATTERNS = {
    'SECURITY': [
        r'invalid user', r'failed password', r'failed none',
        r'authentication failure', r'too many authentication',
        r'more authentication failures', r'possible break-in attempt',
        r'ignoring max retries',
    ],
    'COMPONENT_FAILURE': [
        r'connection closed', r'connection reset', r'received disconnect',
        r'connect_to', r'did not receive identification',
    ],
    'DATA_INTEGRITY': [
        r'bad packet', r'packet corrupt', r'corrupted mac',
        r'bad protocol version',
    ],
    'APPLICATION_ERROR': [
        r'no hostkey alg',
    ],
    'OVERLOAD': [
        r'message repeated',
    ],
}

# Generic/Application logs: no fixed vocabulary exists to ground these in a
# real dataset the way HDFS/SSH's rules are (any application can log
# anything), so these cover the categories LogSense is explicitly asked to
# recognise: auth failures, database/timeout/external-API failures, memory
# and disk problems, and exceptions in general.
#
# Each pattern carries its OWN explanation (not just a category-wide one),
# so a timeout, a connection refusal and an HTTP 503 -- despite all being
# COMPONENT_FAILURE -- each get a description grounded in what that
# specific line actually said, instead of identical boilerplate text.
GENERIC_CAUSE_RULES = {
    'SECURITY': [
        (r'authentication failed', 'A login attempt failed because the '
         'credentials that were provided were not accepted.'),
        (r'auth failed', 'A login or authentication attempt failed.'),
        (r'unauthorized', 'A request was rejected because it lacked valid authentication.'),
        (r'access denied', 'A request was blocked because the user or '
         'process did not have permission to do this.'),
        (r'permission denied', 'The program was not allowed to access something it needed.'),
        (r'invalid credentials', 'Login credentials that were provided did '
         'not match what the system expected.'),
        (r'invalid token', 'A security token used for authentication was invalid or had expired.'),
        (r'forbidden', 'A request was blocked because the caller is not allowed to access this.'),
        (r'\b401\b', 'A request was rejected with an HTTP 401 (Unauthorized) response.'),
        (r'\b403\b', 'A request was rejected with an HTTP 403 (Forbidden) response.'),
    ],
    'COMPONENT_FAILURE': [
        (r'database connection failed|db connection failed', 'The program '
         'could not connect to its database, usually meaning the database '
         'is down, unreachable, or refusing new connections.'),
        (r'sql exception', 'A database query failed to run correctly, '
         'which usually points to a problem with the query itself or the data it touched.'),
        (r'timed? ?out|timeout', 'Something the program depends on (a '
         'database, an API, or another service) took too long to respond, '
         'so the request timed out.'),
        (r'connection refused', 'The program tried to connect to another '
         'service, but that service refused the connection, usually '
         'because it is not running or not listening on the expected address.'),
        (r'connection reset', 'A connection to another service closed '
         'unexpectedly partway through, usually because that service '
         'crashed or dropped the connection.'),
        (r'connection closed', 'A connection to another service closed unexpectedly.'),
        (r'service unavailable|\b502\b|\b503\b|\b504\b', 'A service this '
         'program depends on returned an error saying it is temporarily '
         'unable to handle requests, commonly caused by that service being '
         'overloaded, restarting, or down.'),
        (r'api call failed|failed to call', 'A call to another service or API failed to complete.'),
        (r'upstream.*failed', 'A service further upstream that this program depends on failed.'),
        (r'no route to host', 'The program could not find a network path to another machine.'),
        (r'unreachable', 'Another machine or service could not be reached.'),
    ],
    'RESOURCE': [
        (r'out ?of ?memory|outofmemoryerror', 'The program ran out of '
         'available memory while running, which can cause it to slow down '
         'drastically or crash.'),
        (r'heap space', 'The program ran out of the memory (heap space) it was allowed to use.'),
        (r'gc overhead', 'The program is spending too much time trying to '
         'free up memory, a sign that memory is nearly exhausted.'),
        (r'disk full|no space left', 'The disk this program writes to is completely out of free space.'),
        (r'low disk space|disk usage', 'The disk this program writes to is running low on free space.'),
        (r'memory usage', 'Memory usage on this machine is unusually high.'),
        (r'quota exceeded', 'A configured usage limit (a quota) was exceeded.'),
    ],
    'DATA_INTEGRITY': [
        (r'checksum', 'Data failed a checksum check, meaning it may have been corrupted or altered.'),
        (r'corrupt', 'Data was found to be corrupted or in an unexpected state.'),
        (r'mismatch', 'Data did not match what was expected.'),
        (r'constraint violation', 'A database rule was violated, usually '
         'meaning the data being saved conflicts with existing data or rules.'),
        (r'duplicate key', 'An attempt was made to save a record that already exists.'),
        (r'integrity', 'Data failed an integrity check.'),
    ],
    'APPLICATION_ERROR': [
        (r'null ?pointer', 'The program tried to use something that did '
         'not exist ("null"), a common programming bug.'),
        (r'exception', 'The program hit an exception, an unexpected error, while running.'),
        (r'stack ?trace|traceback', 'The program errored with a stack '
         'trace, showing the exact code path where it failed.'),
        (r'unhandled|uncaught', 'The program hit an error it was not '
         'prepared to handle, usually a bug in its error-handling code.'),
        (r'failed to', 'An operation the program tried to perform did not complete successfully.'),
        (r'\berror\b', 'The program reported an error while handling this operation.'),
    ],
}

# Derived flat {cause: [pattern, ...]} shape for match_causes()/diagnose()'s
# generic interface, and for callers that only need the category, not the
# per-pattern explanation.
GENERIC_CAUSE_PATTERNS = {
    cause: [pattern for pattern, _ in rules] for cause, rules in GENERIC_CAUSE_RULES.items()
}


def match_generic_causes(text):
    """Like match_causes(), but returns each match's own specific
    explanation alongside its cause category, using GENERIC_CAUSE_RULES's
    richer (pattern, explanation) pairs -- so a report can describe what
    was actually found ("a timeout", "a 503") rather than only the broad
    category ("a component failure")."""
    lower = text.lower()
    return [(cause, explanation) for cause, rules in GENERIC_CAUSE_RULES.items()
            for pattern, explanation in rules if re.search(pattern, lower)]

# Vote weight per log level when diagnosing a Generic/Application window --
# a FATAL/CRITICAL line should count for more than a WARN line pointing at
# the same cause category.
GENERIC_LEVEL_WEIGHT = {'WARN': 1, 'WARNING': 1, 'ERROR': 2, 'FATAL': 3, 'CRITICAL': 3}
GENERIC_SUSPICIOUS_LEVELS = frozenset(GENERIC_LEVEL_WEIGHT)

# The severity shown to the user is the worst log level actually seen, not
# whichever cause category happens to win the keyword vote -- a single
# FATAL line shouldn't get diluted to "HIGH" just because a less severe
# WARN-level issue repeated more often in the same window.
GENERIC_LEVEL_SEVERITY = {
    'WARN': 'MEDIUM', 'WARNING': 'MEDIUM',
    'ERROR': 'HIGH',
    'FATAL': 'CRITICAL', 'CRITICAL': 'CRITICAL',
}


def diagnose_generic(unit_records):
    """Cause diagnosis for the Generic/Application pipeline.

    Unlike `diagnose()`, which votes from deviation against a pretrained
    baseline, this looks directly at each flagged line's own text -- there
    is no pretrained baseline for an arbitrary application's log vocabulary,
    so the evidence has to come from the actual WARN+/ERROR+ lines found in
    this window rather than a statistical comparison.

    A single window can easily contain several genuinely different problems
    (a timeout, an auth failure, and an unrelated exception, say), so each
    evidence group is tagged with its OWN best-matched cause AND its own
    specific explanation (via match_generic_causes) -- not just whichever
    cause wins the overall vote -- so the report can explain each line on
    its own terms instead of forcing one blended, generic explanation onto
    every line regardless of what it actually said.
    """
    votes = Counter()
    groups = {}  # (level, text) -> {'count', 'timestamp', 'cause', 'explanation'}

    for record in unit_records:
        level = (record.get('level') or '').upper()
        if level not in GENERIC_SUSPICIOUS_LEVELS:
            continue
        text = record.get('content') or ''
        weight = GENERIC_LEVEL_WEIGHT[level]
        matched = match_generic_causes(text)
        if matched:
            cause, explanation = matched[0]
        else:
            cause, explanation = 'APPLICATION_ERROR', None
        for c, _ in matched:
            votes[c] += weight
        if not matched:
            votes['APPLICATION_ERROR'] += weight

        key = (level, text)
        group = groups.setdefault(
            key, {'count': 0, 'timestamp': record.get('timestamp'),
                  'cause': cause, 'explanation': explanation})
        group['count'] += 1

    # Repeated identical messages collapse into one evidence line with a
    # count, rather than the same line shown many times over. Ranked by
    # severity first, then by repeat count -- a single FATAL line must
    # always be visible in the evidence, even if some lower-severity
    # message happened to repeat more often in the same window (otherwise
    # the reported severity wouldn't be backed by anything shown to the user).
    ranked_groups = sorted(groups.items(),
                            key=lambda kv: (-GENERIC_LEVEL_WEIGHT[kv[0][0]], -kv[1]['count']))
    evidence = [
        {'level': level, 'text': text, 'count': group['count'],
         'timestamp': group['timestamp'], 'cause': group['cause'],
         'explanation': group['explanation']}
        for (level, text), group in ranked_groups[:5]
    ]

    ranked = sorted(votes.items(), key=lambda kv: -kv[1])
    return {
        'primary_cause': ranked[0][0] if ranked else 'UNKNOWN',
        'all_causes': [c for c, _ in ranked],
        'evidence': evidence,
    }


INCOMPLETE_THRESHOLD = 0.6


def match_causes(template_text, patterns=CAUSE_PATTERNS):
    """Return the cause categories a template text matches."""
    text = template_text.lower()
    return [cause for cause, cause_patterns in patterns.items()
            if any(re.search(p, text) for p in cause_patterns)]


def diagnose(explanation, template_map, volume_ratio=1.0, patterns=CAUSE_PATTERNS,
             missing_cause='INCOMPLETE_EXECUTION'):
    """Turn raw excess/missing evidence into ranked likely causes.

    `missing_cause` names the category used when a normally-common event
    goes missing -- for HDFS that means a multi-step operation was cut
    short ('INCOMPLETE_EXECUTION'). Log types without that pipeline-step
    structure (e.g. SSH) pass a differently-worded category instead, since
    "the operation never finished" doesn't describe a shift in which
    login-attempt pattern dominates a window.
    """
    votes = {}
    evidence = []

    for item in explanation['excess']:
        text = template_map[item['event']]
        for cause in match_causes(text, patterns):
            votes[cause] = votes.get(cause, 0) + item['deviation']
            evidence.append(f"{text[:70]} occurred {item['observed']:.0f}x "
                            f"(expected {item['expected']})")

    missing_weight = sum(-i['deviation'] for i in explanation['missing'])
    expected_total = sum(i['expected'] for i in explanation['missing'])
    if expected_total and missing_weight / expected_total > INCOMPLETE_THRESHOLD:
        votes[missing_cause] = votes.get(missing_cause, 0) + missing_weight
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