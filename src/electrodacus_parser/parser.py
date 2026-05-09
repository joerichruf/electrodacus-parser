"""SBMS0 USB/UART ASCII frame decoder.

Each frame is exactly 59 ASCII characters in the printable range [35, 125]
('#'..'}'). Each character encodes one base-91 digit as ``ord(c) - 35``.
Multi-digit fields are concatenated as big-endian base-91. The frame layout
is fixed-position; there is no start/end byte sequence beyond the printable
range itself.

Reference: ``convert2.c`` posted to the Electrodacus Google Group; see
README.md for the link.
"""

from __future__ import annotations

from dataclasses import dataclass

SBMS0_LINE_LEN = 59
_BASE91 = 91
_BASE91_2 = 91 * 91  # 8281
_TEMP_OFFSET_DECI_C = 450
_CRC_BIAS = 1995

_BATT_SIGN_NEG = 10
_BATT_SIGN_POS = 8


@dataclass(frozen=True)
class Sbms0Record:
    """One decoded SBMS0 frame.

    Native protocol units are preserved:
    - cell voltages: millivolts
    - ``it_deci_c`` / ``et_deci_c``: deci-degrees Celsius (215 == 21.5°C)
    - currents (``batt_ma`` etc.): milliamps; ``batt_ma`` is signed

    ``crc_residual`` is 0 when the frame's checksum matches. Any other
    value means at least one base-91 digit was corrupted in transit; the
    other fields on this record cannot be trusted.
    """

    line_no: int
    year: int
    month: int
    day: int
    hour: int
    minute: int
    second: int
    soc: int
    cells_mv: tuple[int, int, int, int, int, int, int, int]
    it_deci_c: int
    et_deci_c: int
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
    crc_residual: int

    @property
    def crc_ok(self) -> bool:
        return self.crc_residual == 0

    @property
    def it_c(self) -> float:
        return self.it_deci_c / 10.0

    @property
    def et_c(self) -> float:
        return self.et_deci_c / 10.0


def looks_like_sbms0_line(s: str) -> bool:
    if len(s) != SBMS0_LINE_LEN:
        return False
    return all(35 <= ord(c) <= 125 for c in s)


def decode_line(line: str, *, line_no: int = 0) -> Sbms0Record | None:
    """Decode one SBMS0 frame.

    Returns ``None`` if the line is structurally invalid: wrong length,
    out-of-range characters, or an unrecognized battery-current sign byte.
    A returned record may still have ``crc_ok == False`` — callers must
    check before trusting the values.
    """

    raw = line.rstrip("\r\n")
    if not looks_like_sbms0_line(raw):
        return None

    a = [ord(c) - 35 for c in raw]

    def b2(i: int) -> int:
        return a[i] * _BASE91 + a[i + 1]

    def b3(i: int) -> int:
        return a[i] * _BASE91_2 + a[i + 1] * _BASE91 + a[i + 2]

    sign_byte = a[28]
    magnitude = b3(29)
    if sign_byte == _BATT_SIGN_NEG:
        batt_ma = -magnitude
    elif sign_byte == _BATT_SIGN_POS:
        batt_ma = magnitude
    else:
        return None

    crc_encoded = a[54] * _BASE91 + a[55]
    digit_sum = sum(a) - a[54] - a[55] + _CRC_BIAS
    crc_residual = crc_encoded - digit_sum

    return Sbms0Record(
        line_no=line_no,
        year=a[0],
        month=a[1],
        day=a[2],
        hour=a[3],
        minute=a[4],
        second=a[5],
        soc=b2(6),
        cells_mv=(
            b2(8), b2(10), b2(12), b2(14),
            b2(16), b2(18), b2(20), b2(22),
        ),
        it_deci_c=b2(24) - _TEMP_OFFSET_DECI_C,
        et_deci_c=b2(26) - _TEMP_OFFSET_DECI_C,
        batt_ma=batt_ma,
        pv1_ma=b3(32),
        pv2_ma=b3(35),
        ext_ma=b3(38),
        pvdiv=b3(41),
        adc3=b3(44),
        adc2=b3(47),
        dmppt=b3(50),
        pv_level=a[53],
        stat=b3(56),
        crc_residual=crc_residual,
    )


@dataclass(frozen=True)
class DecodeStats:
    total_lines: int
    skipped_blank: int
    skipped_malformed: int
    crc_failures: int


def decode_records(
    text: str, *, require_crc: bool = True
) -> tuple[list[Sbms0Record], DecodeStats]:
    """Decode every line in ``text``.

    With ``require_crc=True`` (default), records whose checksum does not
    match are excluded from the returned list but still counted in the
    stats. Pass ``require_crc=False`` for diagnostic flows that need to
    see every structurally-valid frame.
    """

    out: list[Sbms0Record] = []
    total = blank = malformed = crc_fail = 0
    for idx, line in enumerate(text.splitlines(), start=1):
        total += 1
        if not line.strip():
            blank += 1
            continue
        rec = decode_line(line, line_no=idx)
        if rec is None:
            malformed += 1
            continue
        if not rec.crc_ok:
            crc_fail += 1
            if require_crc:
                continue
        out.append(rec)
    return out, DecodeStats(
        total_lines=total,
        skipped_blank=blank,
        skipped_malformed=malformed,
        crc_failures=crc_fail,
    )


def hex_dump(data: bytes, *, width: int = 16) -> str:
    lines: list[str] = []
    for i in range(0, len(data), width):
        chunk = data[i : i + width]
        hex_part = " ".join(f"{b:02x}" for b in chunk)
        ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        lines.append(f"{i:08x}  {hex_part:<{width * 3}}  {ascii_part}")
    return "\n".join(lines)
