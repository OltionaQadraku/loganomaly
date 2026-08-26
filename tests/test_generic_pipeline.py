from api.pipeline import guess_format


def test_generic_parse_valid_lines(generic_pipeline, valid_generic_text):
    records, skipped, sample_skipped = generic_pipeline.parse(valid_generic_text)
    assert len(records) == 5
    assert skipped == 0
    assert sample_skipped == []


def test_generic_parse_all_invalid_lines_collects_samples(generic_pipeline):
    text = 'this is not a log line\nneither is this\n'
    records, skipped, sample_skipped = generic_pipeline.parse(text)
    assert records == []
    assert skipped == 2


def test_generic_parse_tolerates_missing_timestamp(generic_pipeline):
    records, skipped, _ = generic_pipeline.parse('ERROR Database connection failed')
    assert len(records) == 1
    assert records[0]['timestamp'] is None
    assert records[0]['level'] == 'ERROR'
    assert skipped == 0


def test_generic_parse_extracts_thread_and_logger(generic_pipeline):
    line = ('2026-08-22 14:05:12 ERROR [http-nio-8080-exec-4] com.example.UserService '
            '- Failed to load user requestId=req-1234')
    records, _, _ = generic_pipeline.parse(line)
    assert records[0]['thread'] == 'http-nio-8080-exec-4'
    assert records[0]['logger'] == 'com.example.UserService'
    assert records[0]['requestId'] == 'req-1234'


def test_generic_parse_handles_logfmt_style_level(generic_pipeline):
    line = ('2026-08-15T20:11:15.000Z level=WARN server=web-01 host=shop.example.com '
            'client_ip=192.0.2.12 request_id=req-10003 request="GET /assets/logo.png '
            'HTTP/1.1" status=404 message="Static asset not found"')
    records, skipped, _ = generic_pipeline.parse(line)
    assert skipped == 0
    assert len(records) == 1
    record = records[0]
    assert record['level'] == 'WARN'
    assert record['timestamp'] == '2026-08-15T20:11:15.000Z'
    assert record['content'] == 'Static asset not found'
    assert record['requestId'] == 'req-10003'
    assert record['status_code'] == '404'


def test_generic_analyze_flags_logfmt_style_warn_line(generic_pipeline):
    text = '\n'.join([
        '2026-08-15T20:10:01.000Z level=INFO server=web-01 host=shop.example.com '
        'client_ip=192.0.2.10 request_id=req-10001 request="GET / HTTP/1.1" '
        'status=200 message="Home page loaded successfully"',
        '2026-08-15T20:11:15.000Z level=WARN server=web-01 host=shop.example.com '
        'client_ip=192.0.2.12 request_id=req-10003 request="GET /assets/logo.png '
        'HTTP/1.1" status=404 message="Static asset not found"',
        '2026-08-15T20:12:00.000Z level=ERROR server=web-01 host=shop.example.com '
        'client_ip=192.0.2.13 request_id=req-10004 request="POST /checkout HTTP/1.1" '
        'status=500 message="Payment processing failed"',
    ])
    result = generic_pipeline.analyze(text)
    assert 'error' not in result
    assert result['log_type'] == 'generic'
    assert result['anomalies_found'] == 1


def test_generic_analyze_ignores_a_single_isolated_warning(generic_pipeline):
    text = '\n'.join([
        '2026-08-24 10:00:00 INFO Application started',
        '2026-08-24 10:00:01 INFO Handling request',
        '2026-08-24 10:00:02 WARN Slow query took 600ms',
        '2026-08-24 10:00:03 INFO Request completed',
    ])
    result = generic_pipeline.analyze(text)
    assert result['anomalies_found'] == 0


def test_generic_analyze_flags_two_errors_in_a_small_file(generic_pipeline):
    text = '\n'.join([
        '2026-08-24 10:00:00 INFO Application started',
        '2026-08-24 10:00:01 ERROR Database connection failed',
        '2026-08-24 10:00:02 ERROR Database connection failed',
        '2026-08-24 10:00:03 INFO Retrying',
    ])
    result = generic_pipeline.analyze(text)
    assert result['anomalies_found'] == 1


def test_generic_analyze_does_not_flag_healthy_background_noise(generic_pipeline):
    import random
    rng = random.Random(1)
    lines = []
    t = 0
    for _ in range(600):
        t += rng.randint(1, 4)
        r = rng.random()
        if r < 0.03:
            lines.append(f'2026-08-24 10:{t // 60 % 60:02d}:{t % 60:02d} WARN Slow query took 850ms')
        elif r < 0.045:
            lines.append(f'2026-08-24 10:{t // 60 % 60:02d}:{t % 60:02d} ERROR Failed to send '
                          f'email notification, will retry')
        else:
            lines.append(f'2026-08-24 10:{t // 60 % 60:02d}:{t % 60:02d} INFO Request handled successfully')

    result = generic_pipeline.analyze('\n'.join(lines))
    assert result['anomalies_found'] == 0
    assert result['risk_level'] is None


def test_generic_parse_attaches_stack_trace_to_previous_line(generic_pipeline):
    text = (
        '2026-08-22 14:06:10 ERROR java.lang.NullPointerException\n'
        '\tat com.example.Foo.bar(Foo.java:42)\n'
        '\tat com.example.Foo.baz(Foo.java:99)\n'
    )
    records, skipped, _ = generic_pipeline.parse(text)
    assert len(records) == 1
    assert skipped == 0
    assert 'Foo.bar' in records[0]['content']
    assert 'Foo.baz' in records[0]['content']


def test_generic_group_units_builds_tumbling_windows(generic_pipeline):
    records = [{'level': 'INFO', 'content': 'x'} for _ in range(50)]
    windows = generic_pipeline.group_units(records)
    assert len(windows) == 3
    assert len(windows[0]) == generic_pipeline.WINDOW_SIZE
    assert len(windows[2]) == 50 - 2 * generic_pipeline.WINDOW_SIZE


def test_generic_format_unit_id_is_distinguishable(generic_pipeline):
    assert generic_pipeline.format_unit_id(2) == 'window-2'


def test_generic_analyze_on_valid_file_returns_generic_shape(generic_pipeline, valid_generic_text):
    result = generic_pipeline.analyze(valid_generic_text)
    assert 'error' not in result
    assert result['log_type'] == 'generic'
    assert result['total_sessions'] == 1
    assert result['anomalies_found'] == 1


def test_generic_analyze_ignores_purely_informational_logs(generic_pipeline):
    text = '\n'.join([
        '2026-08-22 14:00:00 INFO Application started',
        '2026-08-22 14:00:01 INFO Handling request',
        '2026-08-22 14:00:02 DEBUG Cache hit',
    ])
    result = generic_pipeline.analyze(text)
    assert result['anomalies_found'] == 0
    assert result['risk_level'] is None


def test_generic_analyze_on_unrecognised_format_returns_error_payload(generic_pipeline):
    result = generic_pipeline.analyze('just some plain text with no log level at all')
    assert 'error' in result
    assert result['skipped_lines'] == 1


def test_generic_severity_reflects_worst_level_not_winning_cause(generic_pipeline):
    text = '\n'.join([
        '2026-08-22 14:05:12 ERROR Database connection failed',
        '2026-08-22 14:05:13 ERROR Database connection failed',
        '2026-08-22 14:05:14 ERROR Database connection failed',
        '2026-08-22 14:09:00 FATAL OutOfMemoryError: Java heap space',
    ])
    result = generic_pipeline.analyze(text)
    assert result['anomalies_found'] == 1
    assert result['anomalies'][0]['severity'] == 'CRITICAL'
    assert result['risk_level'] == 'CRITICAL'


def test_generic_repeated_errors_are_grouped_with_a_count(generic_pipeline):
    text = '\n'.join(['2026-08-22 14:05:12 ERROR Database connection failed'] * 5)
    result = generic_pipeline.analyze(text)
    report = result['anomalies'][0]['report']
    assert 'happened 5 times' in report


def test_guess_format_detects_generic_when_uploaded_to_a_different_log_type():
    generic_lines = [
        '2026-08-22 14:05:12 ERROR Database connection failed',
    ]
    assert guess_format(generic_lines) == 'generic'
