from pathlib import Path

from app.log_parser import GenesisLogParser, detect_slot_error, detect_error_lines

FIXTURE = Path(__file__).parent / "fixtures" / "sample_run.log"


def test_parses_fixture_log_in_one_shot():
    parser = GenesisLogParser()
    records = parser.feed(FIXTURE.read_text())

    assert len(records) == 3
    assert records[0].step == 0
    assert records[0].time_ps == 0.0
    assert records[0].values["TOTAL_ENE"] == -1234.50
    assert records[0].values["NATIVE_CONTACT"] == 0.850
    assert records[-1].step == 2000


def test_ignores_non_info_lines_and_header():
    parser = GenesisLogParser()
    records = parser.feed(FIXTURE.read_text())
    assert parser.columns == [
        "STEP", "TIME", "TOTAL_ENE", "POTENTIAL_ENE", "KINETIC_ENE",
        "TEMPERATURE", "NATIVE_CONTACT", "CG_EXV",
    ]
    assert len(records) == len(parser.records)


def test_incremental_feed_matches_single_shot():
    text = FIXTURE.read_text()
    lines = text.splitlines(keepends=True)

    incremental = GenesisLogParser()
    all_records = []
    for line in lines:
        all_records.extend(incremental.feed(line))

    one_shot = GenesisLogParser()
    one_shot_records = one_shot.feed(text)

    assert len(all_records) == len(one_shot_records) == 3
    for a, b in zip(all_records, one_shot_records):
        assert a.step == b.step
        assert a.values == b.values


def test_feed_handles_split_mid_line():
    parser = GenesisLogParser()
    # Header first
    parser.feed("INFO:       STEP       TIME   TOTAL_ENE\n")
    # A data line arrives in two chunks, split mid-token
    r1 = parser.feed("INFO:          0     0.0")
    assert r1 == []
    r2 = parser.feed("000    -1234.50\n")
    assert len(r2) == 1
    assert r2[0].step == 0
    assert r2[0].values["TOTAL_ENE"] == -1234.50


def test_latest():
    parser = GenesisLogParser()
    parser.feed(FIXTURE.read_text())
    assert parser.latest().step == 2000


def test_empty_feed_returns_empty():
    parser = GenesisLogParser()
    assert parser.feed("") == []


def test_detect_slot_error():
    text = "There are not enough slots available in the system.\n"
    assert detect_slot_error(text)
    assert not detect_slot_error("everything is fine\n")


def test_detect_error_lines():
    text = "step 1 ok\nERROR: something broke\nstep 2 ok\n"
    errors = detect_error_lines(text)
    assert len(errors) == 1
    assert "ERROR" in errors[0]
