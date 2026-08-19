import re

CAUSE_INFO = {
    'OVERLOAD': {
        'title': 'The system was under heavy load',
        'meaning': 'Requests arrived faster than the system could handle them, '
                   'so operations started waiting and timing out.',
        'check': 'Check traffic volume and resource usage around this time. '
                 'Consider whether capacity needs to be increased.',
        'severity': 'HIGH',
    },
    'COMPONENT_FAILURE': {
        'title': 'A part of the system stopped responding',
        'meaning': 'One machine or service became unreachable, so the work '
                   'that depended on it could not continue.',
        'check': 'Identify which machine or service was involved and check '
                 'whether it went offline or lost network connectivity.',
        'severity': 'HIGH',
    },
    'INCOMPLETE_EXECUTION': {
        'title': 'The operation started but never finished',
        'meaning': 'Steps that normally happen every single time did not '
                   'happen at all. The process was interrupted partway through.',
        'check': 'Check whether the process was killed, the machine restarted, '
                 'or a dependency became unavailable mid-operation.',
        'severity': 'HIGH',
    },
    'RESOURCE': {
        'title': 'The system ran out of resources',
        'meaning': 'Memory, disk space or another limit was reached, so the '
                   'operation could not be completed.',
        'check': 'Check disk space, memory usage and configured quotas.',
        'severity': 'HIGH',
    },
    'SECURITY': {
        'title': 'Access was refused',
        'meaning': 'Someone or something tried to perform an action it was '
                   'not permitted to perform.',
        'check': 'Review who made these requests and whether the attempts '
                 'were legitimate.',
        'severity': 'CRITICAL',
    },
    'DATA_INTEGRITY': {
        'title': 'The data was damaged or did not match',
        'meaning': 'The system detected that data was corrupted, incomplete '
                   'or different from what was expected.',
        'check': 'Verify the affected data and check the storage hardware.',
        'severity': 'CRITICAL',
    },
    'RECOVERY_ACTION': {
        'title': 'The system had to repair itself',
        'meaning': 'Something failed earlier, and the system automatically '
                   'took corrective action such as retrying or moving the work '
                   'elsewhere. The recovery worked, but the original problem remains.',
        'check': 'Find what triggered the recovery. Repeated recoveries usually '
                 'point to an unstable component.',
        'severity': 'MEDIUM',
    },
    'APPLICATION_ERROR': {
        'title': 'The software reported an error',
        'meaning': 'The program itself raised an error while handling this operation.',
        'check': 'Review the error message and the code path involved.',
        'severity': 'MEDIUM',
    },
    'UNKNOWN': {
        'title': 'Unusual behaviour with no clear cause',
        'meaning': 'This session behaved differently from normal, but the pattern '
                   'does not match any known failure type.',
        'check': 'Review the raw log lines manually.',
        'severity': 'LOW',
    },
}

PLACEHOLDERS = re.compile(r'<[A-Z*]+>')


def humanize_template(text, max_words=10):
    """Turn a raw log template into a short readable phrase."""
    text = PLACEHOLDERS.sub('', text)
    text = re.sub(r'java\.[\w.]+', '', text)
    text = re.sub(r'BLOCK\*|[\w]+\$[\w]+|[\w]+\.[\w]+:', '', text)
    text = re.sub(r'[^a-zA-Z0-9 ,.\-]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip().rstrip('.,:')
    words = text.split()
    if len(words) > max_words:
        text = ' '.join(words[:max_words]) + '...'
    return text[0].upper() + text[1:] if text else 'Unrecognised event'


def _times(count):
    if count == 0:
        return 'never'
    if count == 1:
        return 'once'
    return f'{count:.0f} times'

CAUSE_PREFIX_INFO = {
    'KERN': {
        'title': 'A hardware or system-level fault on the machine itself',
        'meaning': 'This kind of problem comes from the physical machine, not '
                   'from any program running on it -- for example memory, a '
                   'processor, or another physical part having an issue.',
        'check': 'This points at the specific machine named in the evidence '
                 'below. Check that machine for repeated hardware problems.',
        'severity': 'HIGH',
    },
    'APP': {
        'title': 'A program failed to start or run correctly',
        'meaning': 'A submitted program could not run properly -- often '
                   'because of a missing file, a permissions problem, or a '
                   'mistake in how the program was set up. This is usually '
                   'not a hardware fault.',
        'check': 'Check the program and the specific file or resource named '
                 'in the evidence below -- it is likely missing, misspelled, '
                 'or not accessible.',
        'severity': 'MEDIUM',
    },
    'LINK': {
        'title': 'A network connection problem between machines',
        'meaning': 'Two machines that needed to communicate could not '
                   'connect properly.',
        'check': 'Check the network connection for the machine(s) named in '
                 'the evidence below.',
        'severity': 'HIGH',
    },
    'MON': {
        'title': 'A routine hardware monitoring signal',
        'meaning': 'A sensor on the machine reported a reading. This is '
                   'often informational rather than an active failure.',
        'check': 'Check whether this happened around the same time as other '
                 'problems in this report.',
        'severity': 'LOW',
    },
    'MAS': {
        'title': 'An event from the system that manages the whole machine',
        'meaning': 'The system that oversees the whole machine logged this '
                   'event.',
        'check': 'Check whether this coincides with other problems around '
                 'the same time.',
        'severity': 'MEDIUM',
    },
}
PLAIN_PHRASES = [
    (re.compile(r'no such file or directory', re.I),
     'the program tried to use a file or folder that does not exist'),
    (re.compile(r'permission denied', re.I),
     'the program was not allowed to access something it needed'),
    (re.compile(r'connection refused', re.I),
     'the program could not reach another machine it needed to talk to'),
    (re.compile(r'connection reset', re.I),
     'a connection to another machine closed unexpectedly'),
    (re.compile(r'no route to host', re.I),
     'the program could not find a network path to another machine'),
    (re.compile(r'broken pipe', re.I),
     'a connection to another machine broke unexpectedly'),
    (re.compile(r'timed? ?out', re.I),
     'something took too long to respond'),
    (re.compile(r'out of memory', re.I),
     'the machine ran out of memory'),
    (re.compile(r'not responding|unreachable', re.I),
     'another part of the system stopped responding'),
]


def translate_error_phrase(text):
    """Best-effort plain-English translation of a raw system error phrase.
    Returns None if nothing recognisable was found."""
    for pattern, plain in PLAIN_PHRASES:
        if pattern.search(text):
            return plain
    return None


def _fallback_info(cause):
    """Info block for causes with no curated entry (e.g. a classifier-predicted
    fault code we haven't hand-documented) -- grounded in the code's prefix
    rather than a generic "a classifier decided this" non-answer."""
    for prefix, group in CAUSE_PREFIX_INFO.items():
        if cause.startswith(prefix):
            return dict(group)
    return {
        'title': 'An unusual, specific problem was identified',
        'meaning': 'A trained classifier recognised this as a specific, '
                   'known type of problem, based on the exact wording of '
                   'the log line below.',
        'check': 'Review the evidence line below for the exact wording '
                 'that led to this.',
        'severity': 'MEDIUM',
    }


def get_cause_info(cause):
    """The plain-language (title, meaning, check, severity) block for a cause
    code -- curated where we have one, prefix-grounded fallback otherwise.
    Used both by narrate() and directly by the API, so a short, humanised
    title/severity is available without a caller needing to re-derive it
    from the raw cause code."""
    if cause == 'UNKNOWN':
        return CAUSE_INFO['UNKNOWN']
    return CAUSE_INFO.get(cause) or _fallback_info(cause)


def narrate(explanation, diagnosis, template_map, session_id=None):
    """Produce a plain-language report a non-technical reader can follow."""
    primary_cause = diagnosis['primary_cause']
    curated = CAUSE_INFO.get(primary_cause) if primary_cause != 'UNKNOWN' else CAUSE_INFO['UNKNOWN']
    info = curated or _fallback_info(primary_cause)
    lines = []

    if session_id:
        lines.append(f"Session: {session_id}")
    lines.append(f"Severity: {info['severity']}")
    lines.append(f"\nWhat happened: {info['title']}")
    lines.append(f"\nWhy we think so:")

    if curated is None and diagnosis.get('evidence'):
        for line in diagnosis['evidence'][:3]:
            lines.append(f"  - {line}")
            plain = translate_error_phrase(line)
            if plain:
                lines.append(f"    (in plain terms: {plain})")
    else:
        for item in explanation['excess'][:3]:
            phrase = humanize_template(template_map[item['event']])
            if item['expected'] < 0.1:
                lines.append(f"  - \"{phrase}\" happened {_times(item['observed'])}, "
                             f"but normally never happens at all.")
            else:
                lines.append(f"  - \"{phrase}\" happened {_times(item['observed'])}, "
                             f"instead of the usual {item['expected']:.0f}.")

        for item in explanation['missing'][:3]:
            phrase = humanize_template(template_map[item['event']])
            lines.append(f"  - \"{phrase}\" never happened, "
                         f"although it normally happens {_times(item['expected'])}.")

    lines.append(f"\nWhat this usually means:\n  {info['meaning']}")
    lines.append(f"\nWhat to check:\n  {info['check']}")

    return '\n'.join(lines)