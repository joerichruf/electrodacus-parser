from pathlib import Path

from electrodacus_parser.parser import (
    bits_from_ascii,
    bits_to_bytes,
    decode_sbms0_base91_line,
    iter_sbms0_uart_records,
    load_capture,
    normalize_to_bytes,
    parse_sbms0_uart_line,
)


def test_bits_from_ascii_ignores_whitespace():
    bits = bits_from_ascii(b"1 0\n1\t0")
    assert bits == [1, 0, 1, 0]


def test_bits_to_bytes_msb_first():
    # 1010 0000 = 0xA0 when padded
    b = bits_to_bytes([1, 0, 1, 0], msb_first=True)
    assert b == bytes([0xA0])


def test_normalize_to_bytes_on_sample_data():
    sample = Path(__file__).resolve().parents[1] / "data" / "sample_raw_bits.txt"
    cap = load_capture(sample)
    normalized = normalize_to_bytes(cap)
    assert isinstance(normalized, (bytes, bytearray))
    assert normalized == cap.data


def test_parse_sbms0_uart_line_extracts_seq_and_tail():
    line = "#$$#%T#TG|H.H<H&H.H.H'H+*?##-##*#####################$@5%N("
    rec = parse_sbms0_uart_line(line, line_no=1)
    assert rec is not None
    assert rec.seq == "T"
    assert rec.tail_marker == "$@5%N("
    assert rec.payload.startswith("#TG|")


def test_iter_sbms0_uart_records_reads_multiple_lines():
    text = "\n".join(
        [
            "#$$#%T#TG|H...$@5%N(",
            "#$$#%U#TG|H...$@/%N(",
            "not a record",
        ]
    )
    records = iter_sbms0_uart_records(text)
    assert [r.seq for r in records] == ["T", "U"]


def test_decode_sbms0_base91_line_smoke():
    # 60 chars of '#': arr1[i] = 0 for all i.
    # This yields SOC/cells/temps/currents all computed from zeros and the CRC math is deterministic.
    line = "#" * 60
    rec = decode_sbms0_base91_line(line, line_no=1)
    assert rec is not None
    assert rec.year == 0
    assert rec.soc == 0
    assert rec.cells_mv == (0, 0, 0, 0, 0, 0, 0, 0)
    assert rec.it_c == -450
    assert rec.et_c == -450
    # With all zeros, temp1 becomes 1995 and crc becomes -1995.
    assert rec.crc == -1995
    assert rec.crc_ok is False
