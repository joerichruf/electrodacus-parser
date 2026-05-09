# electrodacus-parser

Parses Electrodacus SBMS0 USB/UART capture data and decodes battery metrics
(SOC, per-cell voltages, temperatures, currents, status, CRC).

The decoder validates each frame's structure and CRC. By default the CLI
drops frames whose CRC does not match — values from a corrupted frame
cannot be trusted.

## Project Layout

- **`src/electrodacus_parser/`** — Library code
- **`tests/`** — pytest tests (regression-pinned against `data/sample_raw_bits.txt`)
- **`data/`** — Sample capture files
- **`docker/`** — Docker configuration and run script

## Requirements

- Python 3.10+
- Docker (optional)

## Installation

```bash
pip install -e .
pip install -e ".[dev]"   # with development dependencies
```

## Usage

### Decode SBMS0 UART log

```bash
electrodacus-parser convert data/sample_raw_bits.txt
```

Each row is one frame. CRC failures are dropped by default; pass
`--include-errors` to see them, or `--exit-on-errors` to make the CLI
exit non-zero if any frame was malformed or failed CRC. A summary line
is always written to stderr:

```
5 record(s) shown, 0 malformed, 1 CRC failure(s), 0 blank line(s) (of 6 total).
```

### Hex dump

```bash
electrodacus-parser hexdump data/sample_raw_bits.txt
```

Reads the file as raw bytes and prints a 16-byte-per-line hex/ASCII dump.

### Docker

```bash
cd docker
./run.sh                        # convert sample_raw_bits.txt
./run.sh convert mycapture.txt  # convert your own capture
./run.sh hexdump mycapture.txt
```

Or directly:

```bash
cd docker
docker-compose run --rm parser convert /data/sample_raw_bits.txt
```

## Library API

```python
from electrodacus_parser import decode_line, decode_records

# One frame at a time:
record = decode_line(line)
if record and record.crc_ok:
    print(record.cells_mv, record.batt_ma)

# Or a whole capture, with stats:
records, stats = decode_records(text)               # CRC-OK only
records, stats = decode_records(text, require_crc=False)  # include failures
```

`decode_line` returns `None` when the frame is structurally invalid (wrong
length, out-of-range characters, or an unrecognized battery-current sign
byte). The returned `Sbms0Record` exposes `crc_ok`, `it_c`/`et_c` (Celsius
properties), and the raw `crc_residual` for diagnostics.

## Development

```bash
pytest
ruff check src/ tests/
mypy --strict src/electrodacus_parser
pre-commit install && pre-commit run --all-files
```

## Capturing SBMS0 Data

Connect via USB (CH340/CH341 serial adapter) and capture:

```bash
stty -F /dev/ttyUSB0 115200 cs8 -cstopb -parenb
cat -v /dev/ttyUSB0 > capture.txt
```

Each captured line is exactly 59 ASCII characters in the printable range
`#`..`}` and looks like:

```
#$$#%T#TG|H.H<H&H.H.H'H+*?##-##*#####################$@5%N(
```

## Protocol notes

Each character encodes one base-91 digit (`ord(c) - 35`); multi-digit
fields are big-endian. Frame layout (0-indexed positions):

| Pos | Field | Encoding |
|----:|-------|----------|
| 0–5 | year, month, day, hour, minute, second | 1 digit each |
| 6–7 | SOC (%) | 2 digits |
| 8–23 | Cells 1–8 (mV) | 2 digits each |
| 24–25 | Internal temp (deci-°C, +450 offset) | 2 digits |
| 26–27 | External temp (deci-°C, +450 offset) | 2 digits |
| 28 | Battery current sign (8=charge, 10=discharge) | 1 digit |
| 29–31 | Battery current magnitude (mA) | 3 digits |
| 32–34 | PV1 current (mA) | 3 digits |
| 35–37 | PV2 current (mA) | 3 digits |
| 38–40 | EXT current (mA) | 3 digits |
| 41–43 | PV divider (raw) | 3 digits |
| 44–46 | ADC ch3 (raw) | 3 digits |
| 47–49 | ADC ch2 (raw) | 3 digits |
| 50–52 | DMPPT counter | 3 digits |
| 53 | PV level | 1 digit |
| 54–55 | CRC | 2 digits |
| 56–58 | Stat (status flags) | 3 digits |

The CRC field equals `sum(other_57_digits) + 1995` (mod nothing; both
sides are small integers). On decode, `crc_residual = crc_encoded -
(sum_of_digits - crc_digits + 1995)`; zero means the frame is intact.

## References

- [convert2.c](https://groups.google.com/g/electrodacus/c/xks0XWsay90?pli=1)
  — Original C decoder this implementation was ported from.
