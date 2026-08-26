from api.pipeline import guess_format


def test_ssh_parse_valid_lines(ssh_pipeline, valid_ssh_text):
    records, skipped, sample_skipped = ssh_pipeline.parse(valid_ssh_text)
    assert len(records) == 3
    assert skipped == 0
    assert sample_skipped == []


def test_ssh_parse_all_invalid_lines_collects_samples(ssh_pipeline):
    text = 'this is not an ssh line\nneither is this\n'
    records, skipped, sample_skipped = ssh_pipeline.parse(text)
    assert records == []
    assert skipped == 2


def test_ssh_group_units_builds_tumbling_windows(ssh_pipeline):
    records = [{'EventId': i % 3, 'content': 'x'} for i in range(250)]
    windows = ssh_pipeline.group_units(records)
    assert len(windows) == 3
    assert len(windows[0]) == 100
    assert len(windows[1]) == 100
    assert len(windows[2]) == 50


def test_ssh_format_unit_id_is_distinguishable_from_hdfs(ssh_pipeline):
    assert ssh_pipeline.format_unit_id(3) == 'window-3'


def test_ssh_analyze_on_valid_file_returns_ssh_shape(ssh_pipeline, valid_ssh_text):
    result = ssh_pipeline.analyze(valid_ssh_text)
    assert 'error' not in result
    assert result['log_type'] == 'ssh'
    assert 'message' in result
    assert result['total_sessions'] == 1


def test_ssh_analyze_on_unrecognised_format_returns_error_payload(ssh_pipeline):
    result = ssh_pipeline.analyze('not a real ssh line at all')
    assert 'error' in result
    assert result['skipped_lines'] == 1


def test_ssh_diagnose_cause_uses_ssh_keyword_rules(ssh_pipeline):
    explanation = {
        'excess': [{'event': 1, 'observed': 5.0, 'expected': 0.0, 'deviation': 5.0}],
        'missing': [],
    }
    unit_records = [{'EventId': 1, 'content': 'Invalid user webmaster from 1.2.3.4'}]
    result = ssh_pipeline.diagnose_cause(explanation, unit_records, volume_ratio=1.0)
    assert result['primary_cause'] == 'SECURITY'
    assert result['evidence']


def test_ssh_diagnose_cause_falls_back_to_unknown_with_no_evidence(ssh_pipeline):
    result = ssh_pipeline.diagnose_cause({'excess': [], 'missing': []}, [], volume_ratio=1.0)
    assert result['primary_cause'] == 'UNKNOWN'


def test_guess_format_detects_ssh_when_uploaded_to_a_different_log_type():
    ssh_lines = [
        'Dec 10 06:55:46 LabSZ sshd[24200]: Invalid user webmaster from 173.234.31.186',
    ]
    assert guess_format(ssh_lines) == 'ssh'
