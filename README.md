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
pip install -e ".[mqtt]"  # add MQTT publishing for `stream`
```

For local development, see [Development setup](#development-setup) below
— it walks through creating an isolated virtualenv from scratch.

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

### Stream live data (daemon)

For continuous monitoring (boat, RV, off-grid system), run the parser as a
long-lived daemon that reads the SBMS0 directly off USB and emits decoded
records as JSON, one per line, to stdout — and optionally to MQTT.

```bash
# Read from /dev/ttyUSB0 forever; emit JSONL on stdout. Reopens the port
# automatically if the USB cable is unplugged.
electrodacus-parser stream /dev/ttyUSB0

# Same, but also publish each record to a local MQTT broker (e.g. the
# Mosquitto built into Victron Venus OS):
electrodacus-parser stream /dev/ttyUSB0 \
    --mqtt-broker localhost --mqtt-topic electrodacus/sbms0

# Read from stdin instead of opening the device directly. Useful for
# testing, replaying captured logs, or if another tool already owns the
# serial port:
cat capture.txt | electrodacus-parser stream -
```

Each record is a single JSON object on its own line:

```json
{"received_at":"2026-05-09T12:34:56Z","line_no":1,"device_timestamp":"00-01-01T00:02:49","soc_pct":49,"cells_mv":[3365,3378,3392,3370,3378,3378,3371,3375],"internal_temp_c":21.5,"external_temp_c":-45.0,"battery_ma":-7,"pv1_ma":0,"pv2_ma":0,"ext_ma":0,"stat":20480,"pv_level":1,"pvdiv":0,"adc2":0,"adc3":0,"dmppt":0,"crc_ok":true,"crc_residual":0}
```

Stream flags:

| Flag | Default | Notes |
|------|---------|-------|
| `--baud N` | `115200` | Baud rate when input is a serial device. |
| `--include-errors` | off | Publish CRC-failed records too (with `crc_ok:false`). |
| `--no-stdout` | off | Suppress JSONL output; only useful with `--mqtt-broker`. |
| `--once` | off | Read until EOF and exit (default reopens the serial port forever). |
| `--reconnect-delay SECS` | `2.0` | Cooldown between reconnect attempts. |
| `--mqtt-broker HOST` | — | Enables MQTT publishing. |
| `--mqtt-port N` | `1883` | |
| `--mqtt-topic T` | `electrodacus/sbms0` | |
| `--mqtt-qos {0,1,2}` | `0` | |
| `--mqtt-username U` | — | Password is read from `$MQTT_PASSWORD` (or `--mqtt-password-env VAR`). |

MQTT support requires the optional dependency: `pip install
'electrodacus-parser[mqtt]'`.

### Running on Victron Venus OS with Node-RED

Venus OS ships with a Mosquitto broker on `localhost:1883` and Node-RED.
The cleanest pattern is:

1. Install the package on the GX device (or run it from Docker against
   the device's `/dev/ttyUSB0`).
2. Run the parser as a service that publishes to MQTT:

   ```bash
   electrodacus-parser stream /dev/ttyUSB0 \
       --mqtt-broker localhost \
       --mqtt-topic electrodacus/sbms0 \
       --no-stdout
   ```

3. In Node-RED, drop an `mqtt in` node subscribed to
   `electrodacus/sbms0` (broker `localhost:1883`, output type *parsed
   JSON object*). The `msg.payload` you receive on each tick is the full
   record dict — feed it into a dashboard, gauge, or whatever
   visualization you want on the touchscreen.

If you'd rather skip MQTT, drop a `daemon` node (from
`node-red-contrib-daemon`) running `electrodacus-parser stream
/dev/ttyUSB0` and parse `msg.payload` as JSON line-by-line.

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

## Development setup

The project has zero required runtime dependencies, but `dev` and `mqtt`
extras are needed for tests and MQTT publishing. Set up an isolated
virtualenv inside the project — never share one with another repo.

```bash
cd ~/git/electrodacus-parser

# 1. Make sure no other venv is active. If $VIRTUAL_ENV is set to
#    something outside this repo, run `deactivate` until it's empty.
deactivate 2>/dev/null || true
echo "VIRTUAL_ENV=$VIRTUAL_ENV"   # should be empty

# 2. Create a project-local venv.
python3 -m venv .venv

# 3. Activate it.
source .venv/bin/activate

# 4. Sanity check — every tool should resolve INSIDE this repo.
which python      # → ~/git/electrodacus-parser/.venv/bin/python
which pip         # → ~/git/electrodacus-parser/.venv/bin/pip

# 5. Install the package and dev/mqtt extras.
python -m pip install --upgrade pip
pip install -e ".[dev,mqtt]"

# 6. Install the git pre-commit hook.
pre-commit install
```

### Running checks

```bash
pytest                                       # 27 tests
ruff check src/ tests/
mypy --strict src/electrodacus_parser
pre-commit run --all-files
```

### Troubleshooting

**`ModuleNotFoundError: No module named 'pip'` / `'pre_commit'` and the
traceback points at a path like `/home/you/git/some-other-repo/.venv/`.**

Your shell is auto-activating a different project's virtualenv. The
prompt's `(.venv)` is misleading — what matters is `which python`. Fix:

```bash
# Confirm where the wrong env is coming from.
which python
echo "$VIRTUAL_ENV"

# Deactivate it (may need to run more than once if nested).
deactivate

# Inspect your shell rc files for an auto-activate line and remove it.
grep -E 'activate|VIRTUAL_ENV' ~/.bashrc ~/.zshrc ~/.profile 2>/dev/null

# Then redo the venv steps above for THIS repo.
```

**`python3 -m venv` says `ensurepip is not available`.**
On Debian/Ubuntu: `sudo apt install python3-venv`.

**Tests fail with `ModuleNotFoundError: No module named 'electrodacus_parser'`.**
You skipped the editable install. Run `pip install -e ".[dev]"` again
inside the activated venv.

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
