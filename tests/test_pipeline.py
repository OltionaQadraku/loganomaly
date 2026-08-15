from api.pipeline import guess_format


def test_parse_valid_lines(pipeline, valid_hdfs_text):
    records, skipped, sample_skipped = pipeline.parse(valid_hdfs_text)
    assert len(records) == 3
    assert skipped == 0
    assert sample_skipped == []


def test_parse_all_invalid_lines_collects_samples(pipeline):
    text = 'this is not a log line\nneither is this\n'
    records, skipped, sample_skipped = pipeline.parse(text)
    assert records == []
    assert skipped == 2
    assert sample_skipped == ['this is not a log line', 'neither is this']


def test_analyze_on_unrecognised_format_returns_error_payload(pipeline):
    result = pipeline.analyze('not a real log line at all')
    assert 'error' in result
    assert result['skipped_lines'] == 1
    assert result['sample_lines']


def test_analyze_on_valid_file_returns_success_message(pipeline, valid_hdfs_text):
    result = pipeline.analyze(valid_hdfs_text)
    assert 'error' not in result
    assert 'message' in result
    assert result['warnings'] == []


def test_analyze_warns_on_high_skip_ratio(pipeline, valid_hdfs_text):
    garbage = '\n'.join(f'garbage line {i}' for i in range(10))
    result = pipeline.analyze(valid_hdfs_text + '\n' + garbage)
    assert 'error' not in result
    assert any('did not match' in w for w in result['warnings'])


def test_guess_format_recognises_apache_access_log():
    apache_lines = [
        '127.0.0.1 - - [10/Oct/2023:13:55:36 +0000] "GET /index.html HTTP/1.1" 200 2326',
        '127.0.0.1 - - [10/Oct/2023:13:55:37 +0000] "GET /about.html HTTP/1.1" 404 512',
    ]
    assert guess_format(apache_lines) == 'apache'


def test_guess_format_returns_none_for_unstructured_text():
    assert guess_format(['just some prose', 'about nothing in particular']) is None


def test_guess_format_returns_none_for_empty_input():
    assert guess_format([]) is None
