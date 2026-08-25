from src.diagnose import match_causes, diagnose, SSH_CAUSE_PATTERNS, GENERIC_CAUSE_PATTERNS, diagnose_generic


def test_overload_keywords_match():
    assert 'OVERLOAD' in match_causes('Connection timed out while waiting')


def test_data_integrity_keywords_match():
    assert 'DATA_INTEGRITY' in match_causes('BlockInfo not found in volumeMap.')


def test_recovery_action_keywords_match():
    assert 'RECOVERY_ACTION' in match_causes('Reopen Block for retransmission')


def test_security_keywords_match():
    assert 'SECURITY' in match_causes('Authentication failed: permission denied')


def test_unrelated_text_matches_nothing():
    assert match_causes('Verification succeeded for the block') == []


def test_diagnose_picks_highest_voted_cause():
    explanation = {
        'excess': [{'event': 1, 'observed': 5.0, 'expected': 0.0, 'deviation': 5.0}],
        'missing': [],
    }
    template_map = {1: 'Connection refused, node unreachable'}
    result = diagnose(explanation, template_map, volume_ratio=1.0)
    assert result['primary_cause'] == 'COMPONENT_FAILURE'
    assert result['evidence']


def test_diagnose_detects_incomplete_execution():
    explanation = {
        'excess': [],
        'missing': [
            {'event': 1, 'observed': 0.0, 'expected': 3.0, 'deviation': -3.0},
        ],
    }
    template_map = {1: 'Received block of size from'}
    result = diagnose(explanation, template_map, volume_ratio=1.0)
    assert result['primary_cause'] == 'INCOMPLETE_EXECUTION'


def test_diagnose_falls_back_to_unknown_with_no_evidence():
    explanation = {'excess': [], 'missing': []}
    result = diagnose(explanation, {}, volume_ratio=1.0)
    assert result['primary_cause'] == 'UNKNOWN'


def test_ssh_security_keywords_match():
    assert 'SECURITY' in match_causes('Failed password for invalid user webmaster', SSH_CAUSE_PATTERNS)
    assert 'SECURITY' in match_causes('Invalid user test9 from 52.80.34.196', SSH_CAUSE_PATTERNS)


def test_ssh_component_failure_keywords_match():
    assert 'COMPONENT_FAILURE' in match_causes('Connection closed by 212.47.254.145 [preauth]', SSH_CAUSE_PATTERNS)


def test_ssh_data_integrity_keywords_match():
    assert 'DATA_INTEGRITY' in match_causes('Bad packet length 42. [preauth]', SSH_CAUSE_PATTERNS)


def test_ssh_patterns_dont_leak_hdfs_categories():
    # 'Invalid user' should read as SECURITY under SSH rules, not
    # APPLICATION_ERROR the way a generic 'invalid' keyword would under HDFS's.
    assert match_causes('Invalid user webmaster from 1.2.3.4', SSH_CAUSE_PATTERNS) == ['SECURITY']


def test_diagnose_missing_cause_is_customisable():
    explanation = {
        'excess': [],
        'missing': [
            {'event': 1, 'observed': 0.0, 'expected': 3.0, 'deviation': -3.0},
        ],
    }
    template_map = {1: 'Failed password for root from 1.2.3.4 port 22 ssh2'}
    result = diagnose(explanation, template_map, volume_ratio=1.0, missing_cause='ACTIVITY_SHIFT')
    assert result['primary_cause'] == 'ACTIVITY_SHIFT'


def test_generic_security_keywords_match():
    assert 'SECURITY' in match_causes('Authentication failed for user admin', GENERIC_CAUSE_PATTERNS)
    assert 'SECURITY' in match_causes('Access denied: invalid credentials', GENERIC_CAUSE_PATTERNS)


def test_generic_resource_keywords_match():
    assert 'RESOURCE' in match_causes('OutOfMemoryError: Java heap space', GENERIC_CAUSE_PATTERNS)
    assert 'RESOURCE' in match_causes('disk full, no space left on device', GENERIC_CAUSE_PATTERNS)


def test_generic_component_failure_keywords_match():
    assert 'COMPONENT_FAILURE' in match_causes('Database connection failed', GENERIC_CAUSE_PATTERNS)
    assert 'COMPONENT_FAILURE' in match_causes('Request to payment-service timed out', GENERIC_CAUSE_PATTERNS)


def test_diagnose_generic_ignores_info_and_debug_lines():
    unit_records = [
        {'level': 'INFO', 'content': 'Application started'},
        {'level': 'DEBUG', 'content': 'Cache warmed'},
    ]
    result = diagnose_generic(unit_records)
    assert result['primary_cause'] == 'UNKNOWN'
    assert result['evidence'] == []


def test_diagnose_generic_votes_by_keyword_and_severity():
    unit_records = [
        {'level': 'ERROR', 'content': 'Database connection failed', 'timestamp': '10:00:00'},
        {'level': 'WARN', 'content': 'Memory usage above threshold', 'timestamp': '10:00:01'},
    ]
    result = diagnose_generic(unit_records)
    assert result['primary_cause'] == 'COMPONENT_FAILURE'
    assert any(item['text'] == 'Database connection failed' for item in result['evidence'])


def test_diagnose_generic_collapses_repeated_identical_messages():
    unit_records = [
        {'level': 'ERROR', 'content': 'Database connection failed', 'timestamp': None}
        for _ in range(4)
    ]
    result = diagnose_generic(unit_records)
    assert any(item['count'] == 4 for item in result['evidence'])


def test_diagnose_generic_falls_back_to_application_error_with_no_keyword_match():
    unit_records = [{'level': 'ERROR', 'content': 'something odd happened here', 'timestamp': None}]
    result = diagnose_generic(unit_records)
    assert result['primary_cause'] == 'APPLICATION_ERROR'


def test_diagnose_generic_tags_each_evidence_line_with_its_own_cause():
    # A window mixing very different problems shouldn't get one blended
    # cause for everything -- each line needs its own tag so the report
    # can explain each one specifically.
    unit_records = [
        {'level': 'ERROR', 'content': 'Payment gateway returned HTTP 503', 'timestamp': None},
        {'level': 'ERROR', 'content': 'Authentication failed after multiple attempts', 'timestamp': None},
    ]
    result = diagnose_generic(unit_records)
    causes_by_text = {item['text']: item['cause'] for item in result['evidence']}
    assert causes_by_text['Payment gateway returned HTTP 503'] == 'COMPONENT_FAILURE'
    assert causes_by_text['Authentication failed after multiple attempts'] == 'SECURITY'


def test_diagnose_generic_gives_different_component_failures_different_explanations():
    # Same category (COMPONENT_FAILURE) but different root wording -- a
    # timeout and an HTTP 503 are not the same problem and shouldn't get
    # identical boilerplate.
    unit_records = [
        {'level': 'ERROR', 'content': 'Database connection timeout', 'timestamp': None},
        {'level': 'ERROR', 'content': 'Payment gateway returned HTTP 503', 'timestamp': None},
    ]
    result = diagnose_generic(unit_records)
    explanations_by_text = {item['text']: item['explanation'] for item in result['evidence']}
    timeout_explanation = explanations_by_text['Database connection timeout']
    http503_explanation = explanations_by_text['Payment gateway returned HTTP 503']
    assert timeout_explanation != http503_explanation
    assert 'took too long to respond' in timeout_explanation
    assert 'unable to handle requests' in http503_explanation
