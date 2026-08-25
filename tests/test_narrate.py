from src.narrate import narrate, narrate_generic


def test_narrate_uses_curated_info_for_hdfs_causes():
    explanation = {
        'excess': [{'event': 1, 'observed': 5.0, 'expected': 0.0, 'deviation': 5.0}],
        'missing': [],
    }
    diagnosis = {
        'primary_cause': 'OVERLOAD',
        'all_causes': ['OVERLOAD'],
        'evidence': ['some rule-based evidence line'],
    }
    report = narrate(explanation, diagnosis, {1: 'timeout waiting for <*>'}, 'blk_1')
    assert 'The system was under heavy load' in report
    assert 'some rule-based evidence line' not in report


def test_narrate_shows_real_evidence_for_uncurated_bgl_causes():
    explanation = {'excess': [], 'missing': []}
    diagnosis = {
        'primary_cause': 'KERNPROG',
        'all_causes': ['KERNPROG'],
        'evidence': ['"program check interrupt" occurred 1x -> classified as KERNPROG'],
    }
    report = narrate(explanation, diagnosis, {}, 'window-2')
    assert 'program check interrupt' in report
    assert 'hardware or system-level fault on the machine itself' in report
    assert 'KERNPROG' in report


def test_narrate_falls_back_generically_for_unrecognised_prefix():
    diagnosis = {'primary_cause': 'ZZZWEIRD', 'all_causes': ['ZZZWEIRD'], 'evidence': ['"odd text" -> classified as ZZZWEIRD']}
    report = narrate({'excess': [], 'missing': []}, diagnosis, {}, 'window-9')
    assert 'ZZZWEIRD' in report
    assert 'odd text' in report


def test_narrate_uses_curated_info_for_ssh_activity_shift():
    explanation = {
        'excess': [],
        'missing': [{'event': 1, 'observed': 0.0, 'expected': 22.0, 'deviation': -22.0}],
    }
    diagnosis = {
        'primary_cause': 'ACTIVITY_SHIFT',
        'all_causes': ['ACTIVITY_SHIFT'],
        'evidence': [],
    }
    report = narrate(explanation, diagnosis, {1: 'Failed password for root from <*> port <NUM> ssh2'}, 'window-4')
    assert 'usual pattern of activity suddenly changed' in report


def test_narrate_generic_shows_real_flagged_lines_as_evidence():
    diagnosis = {
        'primary_cause': 'COMPONENT_FAILURE',
        'all_causes': ['COMPONENT_FAILURE'],
        'evidence': [{'level': 'ERROR', 'text': 'Database connection failed', 'count': 3,
                      'timestamp': '10:05:12', 'cause': 'COMPONENT_FAILURE'}],
    }
    report = narrate_generic(diagnosis, 'window-0')
    assert 'Database connection failed' in report
    assert 'happened 3 times' in report
    assert 'A part of the system stopped responding' in report


def test_narrate_generic_severity_override_beats_cause_default():
    diagnosis = {'primary_cause': 'COMPONENT_FAILURE', 'all_causes': ['COMPONENT_FAILURE'], 'evidence': []}
    report = narrate_generic(diagnosis, 'window-0', severity='CRITICAL')
    assert 'Severity: CRITICAL' in report


def test_narrate_generic_explains_each_line_with_its_own_cause():
    # A window mixing an external-service failure with an unrelated auth
    # failure shouldn't give both lines the same blended explanation.
    diagnosis = {
        'primary_cause': 'COMPONENT_FAILURE',
        'all_causes': ['COMPONENT_FAILURE', 'SECURITY'],
        'evidence': [
            {'level': 'ERROR', 'text': 'Payment gateway returned HTTP 503', 'count': 1,
             'timestamp': None, 'cause': 'COMPONENT_FAILURE'},
            {'level': 'ERROR', 'text': 'Authentication failed after multiple attempts', 'count': 1,
             'timestamp': None, 'cause': 'SECURITY'},
        ],
    }
    report = narrate_generic(diagnosis, 'window-0')
    assert 'Payment gateway returned HTTP 503' in report
    assert 'Authentication failed after multiple attempts' in report
    # Each line's own explanation should appear (not just the winning cause's).
    assert 'unreachable' in report or 'stopped responding' in report
    assert 'Someone or something tried to perform an action' in report
    assert 'other, different kinds of problems' in report


def test_narrate_translates_common_error_phrases_into_plain_language():
    diagnosis = {
        'primary_cause': 'APPOUT',
        'all_causes': ['APPOUT'],
        'evidence': ['"ciod: LOGIN chdir(/p/bg1/da) failed: No such file or '
                     'directory" occurred 100x -> classified as APPOUT'],
    }
    report = narrate({'excess': [], 'missing': []}, diagnosis, {}, 'window-3')
    assert 'in plain terms' in report
    assert 'file or folder that does not exist' in report
    assert 'ciod' not in report.split('What happened:')[1].split('Why we think so')[0]
