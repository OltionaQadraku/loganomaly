from src.narrate import narrate


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
