from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
import re


@dataclass(frozen=True)
class RawCapture:
    """Raw capture loaded from disk.

    This project starts with a conservative assumption: you have a file containing
    either:
    - ASCII '0'/'1' bit characters (optionally with whitespace), OR
    - raw bytes (binary file) from a USB sniff/trace export.

    As we learn the exact SBMS0 USB framing, higher-level decoding can be layered
    on top of this.
    """

    source_path: Path
    data: bytes


def _is_likely_bittext(data: bytes) -> bool:
    sample = data[:4096]
    allowed = set(b"01 \r\n\t")
    return len(sample) > 0 and all(b in allowed for b in sample)


_HEX_TOKEN_RE = re.compile(r"^(?:0x)?[0-9a-fA-F]{2}$")


def _try_parse_hex_text(data: bytes) -> bytes | None:
    """Parse common 'hex dump' text formats into raw bytes.

    Accepts whitespace-separated 2-hex-digit bytes, optionally prefixed with 0x.
    Returns None if the input doesn't look like hex text.
    """

    try:
        text = data.decode("ascii")
    except UnicodeDecodeError:
        return None

    # Fast reject: if there are non-ascii-printable chars, it's not a hex text file.
    if any(ord(ch) < 9 or (13 < ord(ch) < 32) for ch in text):
        return None

    tokens = [t for t in re.split(r"\s+", text.strip()) if t]
    if not tokens:
        return None

    if not all(_HEX_TOKEN_RE.match(t) for t in tokens):
        return None

    out = bytearray()
    for t in tokens:
        if t.lower().startswith("0x"):
            t = t[2:]
        out.append(int(t, 16))
    return bytes(out)


def bits_from_ascii(data: bytes) -> list[int]:
    bits: list[int] = []
    for ch in data:
        if ch == ord("0"):
            bits.append(0)
        elif ch == ord("1"):
            bits.append(1)
        else:
            continue
    return bits


def bits_to_bytes(bits: Iterable[int], *, msb_first: bool = True) -> bytes:
    out = bytearray()
    acc = 0
    n = 0

    for bit in bits:
        b = 1 if bit else 0
        if msb_first:
            acc = (acc << 1) | b
        else:
            acc = acc | (b << n)

        n += 1
        if n == 8:
            out.append(acc & 0xFF)
            acc = 0
            n = 0

    if n != 0:
        if msb_first:
            acc <<= (8 - n)
        out.append(acc & 0xFF)

    return bytes(out)


def load_capture(path: str | Path) -> RawCapture:
    p = Path(path)
    data = p.read_bytes()
    return RawCapture(source_path=p, data=data)


def normalize_to_bytes(capture: RawCapture, *, msb_first: bool = True) -> bytes:
    """Normalize capture to a byte stream.

    - If the file is hex text, it is parsed into bytes.
    - If the file is ASCII bits, they are packed into bytes.
    - Otherwise, the raw bytes are returned unchanged.
    """

    hex_bytes = _try_parse_hex_text(capture.data)
    if hex_bytes is not None:
        return hex_bytes

    if _is_likely_bittext(capture.data):
        bits = bits_from_ascii(capture.data)
        return bits_to_bytes(bits, msb_first=msb_first)
    return capture.data


def hex_dump(data: bytes, *, width: int = 16) -> str:
    lines: list[str] = []
    for i in range(0, len(data), width):
        chunk = data[i : i + width]
        hex_part = " ".join(f"{b:02x}" for b in chunk)
        ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        lines.append(f"{i:08x}  {hex_part:<{width*3}}  {ascii_part}")
    return "\n".join(lines)


@dataclass(frozen=True)
class Sbms0UartRecord:
    line_no: int
    seq: str | None
    payload: str
    tail_marker: str | None
    raw: str


@dataclass(frozen=True)
class Sbms0DecodedRecord:
    line_no: int
    year: int
    month: int
    day: int
    hour: int
    minute: int
    second: int
    soc: int
    cells_mv: tuple[int, int, int, int, int, int, int, int]
    it_c: int
    et_c: int
    batt_ma: int
    pv1_ma: int
    pv2_ma: int
    ext_ma: int
    pvdiv: int
    adc3: int
    adc2: int
    dmppt: int
    pv_level: int
    stat: int
    crc: int
    crc_ok: bool


_SBMS0_LINE_RE = re.compile(r"^#\$\$#%(.)(.*)$")


def parse_sbms0_uart_line(line: str, *, line_no: int) -> Sbms0UartRecord | None:
    """Parse one SBMS0 UART log line.

    This is intentionally a *minimal* parser that extracts stable structure
    visible in typical `cat -v` output:
    - leading prefix `#$$#%`
    - a one-character sequence marker (often increments: T, U, V, ...)
    - the rest of the line as payload

    It also attempts to split off a trailing marker pattern like `$@X%N(` if
    present.
    """

    raw = line.rstrip("\r\n")
    if not raw:
        return None

    m = _SBMS0_LINE_RE.match(raw)
    if not m:
        return None

    seq = m.group(1)
    payload = m.group(2)

    tail_marker = None
    # Common tail snippet observed in shared logs: `$@<ch>%N(`
    tail_idx = payload.rfind("$@")
    if tail_idx != -1:
        tail_candidate = payload[tail_idx:]
        if len(tail_candidate) >= 5 and tail_candidate.endswith("%N("):
            tail_marker = tail_candidate
            payload = payload[:tail_idx]

    return Sbms0UartRecord(
        line_no=line_no,
        seq=seq,
        payload=payload,
        tail_marker=tail_marker,
        raw=raw,
    )


def iter_sbms0_uart_records(text: str) -> list[Sbms0UartRecord]:
    records: list[Sbms0UartRecord] = []
    for idx, line in enumerate(text.splitlines(), start=1):
        rec = parse_sbms0_uart_line(line, line_no=idx)
        if rec is not None:
            records.append(rec)
    return records


def decode_sbms0_base91_line(line: str, *, line_no: int) -> Sbms0DecodedRecord | None:
    raw = line.rstrip("\r\n")
    if not raw:
        return None

    # convert2.c effectively decodes positions 1..59 (it reads bytes up to newline,
    # and the newline may become the 60th stored character but is not used).
    if len(raw) < 59:
        return None

    arr1 = [0] * 61
    arr3 = [0] * 61
    for i in range(1, 60):
        ch = raw[i - 1]
        arr1[i] = ord(ch) - 35
        arr3[i] = ord(ch)

    year = arr1[1]
    month = arr1[2]
    day = arr1[3]
    hour = arr1[4]
    minute = arr1[5]
    second = arr1[6]

    soc = (arr1[7] * 91) + arr1[8]
    c1 = (arr1[9] * 91) + arr1[10]
    c2 = (arr1[11] * 91) + arr1[12]
    c3 = (arr1[13] * 91) + arr1[14]
    c4 = (arr1[15] * 91) + arr1[16]
    c5 = (arr1[17] * 91) + arr1[18]
    c6 = (arr1[19] * 91) + arr1[20]
    c7 = (arr1[21] * 91) + arr1[22]
    c8 = (arr1[23] * 91) + arr1[24]

    it_c = (arr1[25] * 91) + arr1[26] - 450
    et_c = (arr1[27] * 91) + arr1[28] - 450

    batt_ma = 0
    if arr1[29] == 10:
        batt_ma = -((arr1[30] * 8281) + (arr1[31] * 91) + arr1[32])
    elif arr1[29] == 8:
        batt_ma = (arr1[30] * 8281) + (arr1[31] * 91) + arr1[32]

    pv1_ma = (arr1[33] * 8281) + (arr1[34] * 91) + arr1[35]
    pv2_ma = (arr1[36] * 8281) + (arr1[37] * 91) + arr1[38]
    ext_ma = (arr1[39] * 8281) + (arr1[40] * 91) + arr1[41]

    pvdiv = (arr1[42] * 8281) + (arr1[43] * 91) + arr1[44]
    adc3 = (arr1[45] * 8281) + (arr1[46] * 91) + arr1[47]
    adc2 = (arr1[48] * 8281) + (arr1[49] * 91) + arr1[50]
    dmppt = (arr1[51] * 8281) + (arr1[52] * 91) + arr1[53]

    pv_level = arr1[54]
    stat = (arr1[57] * 8281) + (arr1[58] * 91) + arr1[59]

    temp1 = 0
    for i in range(1, 60):
        temp1 += arr1[i]
    temp1 = (temp1 - arr1[55] - arr1[56]) + 1995
    crc = ((arr1[55] * 91) + arr1[56]) - temp1

    return Sbms0DecodedRecord(
        line_no=line_no,
        year=year,
        month=month,
        day=day,
        hour=hour,
        minute=minute,
        second=second,
        soc=soc,
        cells_mv=(c1, c2, c3, c4, c5, c6, c7, c8),
        it_c=it_c,
        et_c=et_c,
        batt_ma=batt_ma,
        pv1_ma=pv1_ma,
        pv2_ma=pv2_ma,
        ext_ma=ext_ma,
        pvdiv=pvdiv,
        adc3=adc3,
        adc2=adc2,
        dmppt=dmppt,
        pv_level=pv_level,
        stat=stat,
        crc=crc,
        crc_ok=(crc == 0),
    )


def iter_sbms0_decoded_records(text: str) -> list[Sbms0DecodedRecord]:
    out: list[Sbms0DecodedRecord] = []
    for idx, line in enumerate(text.splitlines(), start=1):
        rec = decode_sbms0_base91_line(line, line_no=idx)
        if rec is not None:
            out.append(rec)
    return out
