from pathlib import Path

import pytest
from electrodacus_parser import (
    SBMS0_LINE_LEN,
    Sbms0Record,
    decode_line,
    decode_records,
    hex_dump,
    looks_like_sbms0_line,
)

SAMPLE_PATH = Path(__file__).resolve().parents[1] / "data" / "sample_raw_bits.txt"

SAMPLE_LINE_1 = "#$$#%T#TG|H.H<H&H.H.H'H+*?##-##*#####################$@5%N("
SAMPLE_LINE_3 = "#$$#%V#TG|H.H=H&H/F.H'H,*8##-##&#####################$@/%N("


def test_looks_like_sbms0_line_accepts_valid_frame():
    assert looks_like_sbms0_line(SAMPLE_LINE_1)
    assert len(SAMPLE_LINE_1) == SBMS0_LINE_LEN


def test_looks_like_sbms0_line_rejects_wrong_length():
    assert not looks_like_sbms0_line(SAMPLE_LINE_1[:-1])
    assert not looks_like_sbms0_line(SAMPLE_LINE_1 + "X")


def test_looks_like_sbms0_line_rejects_out_of_range_chars():
    bad = " " + SAMPLE_LINE_1[1:]
    assert not looks_like_sbms0_line(bad)
    bad = SAMPLE_LINE_1[:-1] + "~"
    assert not looks_like_sbms0_line(bad)


def test_decode_line_pinned_values_for_sample_line_1():
    rec = decode_line(SAMPLE_LINE_1, line_no=1)
    assert rec is not None
    assert (rec.year, rec.month, rec.day) == (0, 1, 1)
    assert (rec.hour, rec.minute, rec.second) == (0, 2, 49)
    assert rec.soc == 49
    assert rec.cells_mv == (3365, 3378, 3392, 3370, 3378, 3378, 3371, 3375)
    assert rec.it_deci_c == 215
    assert rec.et_deci_c == -450
    assert rec.batt_ma == -7
    assert rec.pv1_ma == 0
    assert rec.pv2_ma == 0
    assert rec.ext_ma == 0
    assert rec.stat == 20480
    assert rec.crc_residual == 0
    assert rec.crc_ok is True


def test_decode_line_sample_line_3_has_crc_failure():
    rec = decode_line(SAMPLE_LINE_3, line_no=3)
    assert rec is not None
    assert rec.crc_ok is False
    assert rec.crc_residual == 2


def test_decode_line_temperature_properties_scale_to_celsius():
    rec = decode_line(SAMPLE_LINE_1, line_no=1)
    assert rec is not None
    assert rec.it_c == pytest.approx(21.5)
    assert rec.et_c == pytest.approx(-45.0)


def test_decode_line_returns_none_for_short_line():
    assert decode_line("too short") is None


def test_decode_line_returns_none_for_long_line():
    assert decode_line(SAMPLE_LINE_1 + "X") is None


def test_decode_line_returns_none_on_unknown_batt_sign_byte():
    bad = list(SAMPLE_LINE_1)
    bad[28] = "Z"  # ord('Z') - 35 = 55, not 8 or 10
    assert decode_line("".join(bad)) is None


def test_decode_line_returns_none_on_out_of_range_char():
    bad = " " + SAMPLE_LINE_1[1:]
    assert decode_line(bad) is None


def test_decode_records_drops_crc_failures_by_default():
    text = SAMPLE_PATH.read_text(encoding="utf-8")
    records, stats = decode_records(text)
    assert stats.total_lines == 6
    assert stats.crc_failures == 1
    assert stats.skipped_malformed == 0
    assert len(records) == 5
    assert all(r.crc_ok for r in records)


def test_decode_records_includes_crc_failures_when_requested():
    text = SAMPLE_PATH.read_text(encoding="utf-8")
    records, stats = decode_records(text, require_crc=False)
    assert len(records) == 6
    assert stats.crc_failures == 1
    assert sum(1 for r in records if not r.crc_ok) == 1


def test_decode_records_counts_blank_and_malformed():
    text = "\n".join([SAMPLE_LINE_1, "", "garbage", SAMPLE_LINE_1])
    records, stats = decode_records(text)
    assert stats.total_lines == 4
    assert stats.skipped_blank == 1
    assert stats.skipped_malformed == 1
    assert len(records) == 2


def test_sbms0_record_is_frozen_dataclass():
    rec = decode_line(SAMPLE_LINE_1, line_no=1)
    assert rec is not None
    with pytest.raises(Exception):
        rec.soc = 0  # type: ignore[misc]


def test_hex_dump_renders_basic_structure():
    out = hex_dump(b"hello world")
    assert "00000000" in out
    assert "hello world" in out


def test_record_type_is_exposed():
    assert isinstance(Sbms0Record, type)
