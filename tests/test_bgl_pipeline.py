from api.pipeline import guess_format


def test_bgl_parse_valid_lines(bgl_pipeline, valid_bgl_text):
    records, skipped, sample_skipped = bgl_pipeline.parse(valid_bgl_text)
    assert len(records) == 3
    assert skipped == 0
    assert sample_skipped == []


def test_bgl_parse_all_invalid_lines_collects_samples(bgl_pipeline):
    text = 'this is not a bgl line\nneither is this\n'
    records, skipped, sample_skipped = bgl_pipeline.parse(text)
    assert records == []
    assert skipped == 2


def test_bgl_group_units_builds_tumbling_windows(bgl_pipeline):
    records = [{'EventId': i % 3, 'content': 'x'} for i in range(250)]
    windows = bgl_pipeline.group_units(records)
    assert len(windows) == 3
    assert len(windows[0]) == 100
    assert len(windows[1]) == 100
    assert len(windows[2]) == 50


def test_bgl_format_unit_id_is_distinguishable_from_hdfs(bgl_pipeline):
    assert bgl_pipeline.format_unit_id(3) == 'window-3'


def test_bgl_analyze_on_valid_file_returns_bgl_shape(bgl_pipeline, valid_bgl_text):
    result = bgl_pipeline.analyze(valid_bgl_text)
    assert 'error' not in result
    assert result['log_type'] == 'bgl'
    assert 'message' in result
    assert result['total_sessions'] == 1  


def test_bgl_analyze_on_unrecognised_format_returns_error_payload(bgl_pipeline):
    result = bgl_pipeline.analyze('not a real bgl line at all')
    assert 'error' in result
    assert result['skipped_lines'] == 1


def test_bgl_diagnose_cause_uses_trained_classifier(bgl_pipeline):
    explanation = {
        'excess': [{'event': 1, 'observed': 5.0, 'expected': 0.0, 'deviation': 5.0}],
        'missing': [],
    }
    unit_records = [{'EventId': 1, 'content': 'rts panic! - stopping execution'}]
    result = bgl_pipeline.diagnose_cause(explanation, unit_records, volume_ratio=1.0)
    assert result['primary_cause'] == 'KERNRTSP'
    assert result['evidence']


def test_bgl_diagnose_cause_falls_back_to_unknown_with_no_evidence(bgl_pipeline):
    result = bgl_pipeline.diagnose_cause({'excess': [], 'missing': []}, [], volume_ratio=1.0)
    assert result['primary_cause'] == 'UNKNOWN'


def test_guess_format_detects_hdfs_when_uploaded_to_a_different_log_type():
    hdfs_lines = [
        '081109 203607 169 INFO dfs.DataNode$DataXceiver: Receiving block '
        'blk_1 src: /1.1.1.1:1 dest: /1.1.1.1:1',
    ]
    assert guess_format(hdfs_lines) == 'hdfs'


def test_guess_format_detects_bgl_when_uploaded_to_a_different_log_type():
    bgl_lines = [
        '- 1117838570 2005.06.03 R02-M1-N0-C:J12-U11 2005-06-03-15.42.50.675872 '
        'R02-M1-N0-C:J12-U11 RAS KERNEL INFO instruction cache parity error corrected',
    ]
    assert guess_format(bgl_lines) == 'bgl'
