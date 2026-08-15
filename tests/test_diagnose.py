from src.diagnose import match_causes, diagnose


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
