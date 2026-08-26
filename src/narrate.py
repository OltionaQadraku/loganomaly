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
    'ACTIVITY_SHIFT': {
        'title': 'The usual pattern of activity suddenly changed',
        'meaning': 'A kind of event that is normally very common in this '
                   'part of the log stopped happening, while a different '
                   'kind took over. For login logs this often just means a '
                   'different automated source or script became active.',
        'check': 'Compare the source addresses or accounts in the evidence '
                 'below against nearby, unflagged sections to see whether a '
                 'new source took over.',
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
                   'from any program running on it. For example, memory, a '
                   'processor, or another physical part could be having an issue.',
        'check': 'This points at the specific machine named in the evidence '
                 'below. Check that machine for repeated hardware problems.',
        'severity': 'HIGH',
    },
    'APP': {
        'title': 'A program failed to start or run correctly',
        'meaning': 'A submitted program could not run properly. This is often '
                   'because of a missing file, a permissions problem, or a '
                   'mistake in how the program was set up, and is usually '
                   'not a hardware fault.',
        'check': 'Check the program and the specific file or resource named '
                 'in the evidence below. It is likely missing, misspelled, '
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

BGL_CAUSE_INFO = {
    'KERNDTLB': {
        'title': 'A memory-addressing hardware fault on the compute node',
        'meaning': 'The processor hit an error while translating a memory '
                   'address (a "TLB error"), a low-level hardware fault that '
                   'is not something a program did wrong. This is the single '
                   'most common failure type on this system.',
        'check': 'Check the specific compute node named in the evidence '
                 'below for a pattern of repeated memory/TLB errors. That '
                 'usually means failing memory hardware on that node, not a '
                 'one-off glitch.',
        'severity': 'HIGH',
    },
    'KERNSTOR': {
        'title': 'A hardware fault while the processor accessed memory',
        'meaning': 'The processor reported a "data storage interrupt", a '
                   'low-level hardware fault triggered while it tried to '
                   'read or write memory, separate from a normal software error.',
        'check': 'Check the specific compute node named in the evidence '
                 'below for repeated interrupts. That points to a '
                 'hardware problem on that node.',
        'severity': 'HIGH',
    },
    'APPSEV': {
        'title': 'The connection between a program and its control process dropped',
        'meaning': 'The process that manages programs running on the '
                   'compute nodes ("ciod") lost its connection to a node '
                   'partway through starting or running the job. The '
                   'network link was cut.',
        'check': 'Check the compute node and network path named in the '
                 'evidence below for connectivity problems around this time.',
        'severity': 'HIGH',
    },
    'APPUNAV': {
        'title': 'The job could not be started because a required file was unavailable',
        'meaning': 'The process that starts programs on the compute nodes '
                   '("ciod") tried to read a job configuration file (a '
                   '"node map") and the file system reported it as '
                   'temporarily unavailable.',
        'check': 'Check the file named in the evidence below and the '
                 'storage system it lives on. This usually points to a '
                 'busy or overloaded file server rather than a missing file.',
        'severity': 'MEDIUM',
    },
    'KERNMNTF': {
        'title': 'A compute node failed to connect to the shared storage system',
        'meaning': 'The node could not mount "Lustre", the shared file '
                   'system all nodes use to read and write data. Programs '
                   'on that node cannot access files until this is fixed.',
        'check': 'Check the node named in the evidence below and the '
                 'shared storage (Lustre) service for outages.',
        'severity': 'HIGH',
    },
    'KERNTERM': {
        'title': "The compute node's operating system shut itself down",
        'meaning': 'The node\'s low-level runtime system ("rts") detected '
                   'a corrupted or unexpected internal message and '
                   'terminated itself as a safety measure.',
        'check': 'Check the node named in the evidence below. Repeated '
                 'terminations usually mean a hardware or firmware problem '
                 'on that specific node.',
        'severity': 'CRITICAL',
    },
    'KERNREC': {
        'title': 'A network message arrived garbled or out of order',
        'meaning': 'The node\'s internal "tree network" (used to '
                   'coordinate jobs across the machine) received a packet '
                   'that did not match what it expected, a sign of a '
                   'network hardware or timing problem.',
        'check': 'Check the node and network path named in the evidence '
                 'below for repeated occurrences, which usually means a '
                 'faulty network link or card.',
        'severity': 'MEDIUM',
    },
    'APPREAD': {
        'title': 'The program-launching process lost contact with a compute node',
        'meaning': 'The process that starts and monitors programs on the '
                   'compute nodes ("ciod") could not read the next '
                   'expected message from a node, usually because the '
                   'node became unreachable or crashed.',
        'check': 'Check the compute node named in the evidence below. '
                 'This usually happens right after a node fails or loses '
                 'its network connection.',
        'severity': 'HIGH',
    },
    'KERNRTSP': {
        'title': "The compute node's operating system crashed",
        'meaning': 'The node\'s low-level runtime system ("rts") hit a '
                   'fatal internal error ("panic") and stopped everything '
                   'running on that node.',
        'check': 'Check the node named in the evidence below for hardware '
                 'issues. A crash like this usually needs the node '
                 'rebooted and, if it recurs, physically inspected.',
        'severity': 'CRITICAL',
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
    (re.compile(r'broken pipe|link has been severed', re.I),
     'a connection to another machine broke unexpectedly'),
    (re.compile(r'timed? ?out', re.I),
     'something took too long to respond'),
    (re.compile(r'out of memory', re.I),
     'the machine ran out of memory'),
    (re.compile(r'not responding|unreachable', re.I),
     'another part of the system stopped responding'),
    (re.compile(r'resource temporarily unavailable', re.I),
     'the system was too busy to do this right away'),
    (re.compile(r'bad message header', re.I),
     'the two sides of a connection got out of sync with each other'),
    (re.compile(r'lustre mount failed', re.I),
     'the shared storage system could not be connected'),
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
    if cause in BGL_CAUSE_INFO:
        return dict(BGL_CAUSE_INFO[cause])
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


def narrate_generic(diagnosis, session_id=None, severity=None):
    """Report for the Generic/Application pipeline.

    Unlike narrate(), which compares a session's event counts against a
    pretrained baseline, there is no pretrained baseline for an arbitrary
    application's log vocabulary -- so "why we think so" is always the
    actual flagged WARN+/ERROR+ lines themselves (`diagnosis['evidence']`),
    not a statistical deviation. Same report shape either way, so the
    frontend's report parser doesn't need to know the difference.

    A single window can genuinely contain several different problems (a
    timeout, an auth failure and an unrelated exception, say), so each
    evidence line is explained with ITS OWN cause, not just the one that
    happened to win the overall vote for the window -- otherwise a user
    reading the report has no way to tell which explanation applies to
    which line.

    `severity` lets the caller pass the worst log level actually observed
    (FATAL/ERROR/WARN) instead of the cause category's default severity --
    a single FATAL line shouldn't get diluted just because a less severe
    issue happened to win the cause vote.
    """
    info = get_cause_info(diagnosis['primary_cause'])
    lines = []

    if session_id:
        lines.append(f"Session: {session_id}")
    lines.append(f"Severity: {severity or info['severity']}")
    lines.append(f"\nWhat happened: {info['title']}")
    lines.append(f"\nWhy we think so:")

    other_causes = []
    for item in diagnosis['evidence'][:5]:
        prefix = f"[{item['timestamp']}] " if item.get('timestamp') else ''
        times = f" (happened {item['count']} times)" if item.get('count', 1) > 1 else ''
        lines.append(f"  - {prefix}{item['level']}: {item['text'][:150]}{times}")

        item_cause = item.get('cause')
        specific = item.get('explanation')
        if specific:
            lines.append(f"    What this line likely means: {specific}")
        elif item_cause:
            lines.append(f"    What this line likely means: {get_cause_info(item_cause)['meaning']}")
        plain = translate_error_phrase(item['text'])
        if plain:
            lines.append(f"    In plain terms: {plain}")
        if item_cause and item_cause != diagnosis['primary_cause'] and item_cause not in other_causes:
            other_causes.append(item_cause)

    lines.append(f"\nWhat this usually means:\n  {info['meaning']}")
    if other_causes:
        other_titles = '; '.join(get_cause_info(c)['title'] for c in other_causes)
        lines.append(f"\n  This section also shows other, different kinds of problems: "
                     f"{other_titles}. See the notes under each line above for details "
                     f"on that specific one.")
    lines.append(f"\nWhat to check:\n  {info['check']}")

    return '\n'.join(lines)


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