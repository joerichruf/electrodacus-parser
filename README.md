# electrodacus-parser
Parses Electrodacus SBMS0 USB capture data.

This repository is intentionally starting with a small, format-agnostic foundation:
it can load a capture file that is either raw binary bytes or an ASCII file
containing `0`/`1` bits (with optional whitespace), normalize it into a byte
stream, and print a hex dump.

As you provide the exact SBMS0 USB framing (packet boundaries, checksums, field
layout, endianness), we can layer a real SBMS0 message decoder on top.

## Project layout
- **`src/electrodacus_parser/`**: library code
- **`tests/`**: pytest tests
- **`data/`**: sample capture files
- **`docker/`**: Docker configuration, docker-compose, and run script

## Requirements
- Python 3.10+

## Install (editable)
```bash
python -m pip install -e .
```

If you don't want to install it yet, you can run the CLI directly via Python:
```bash
python -m electrodacus_parser.cli hexdump data/sample_raw_bits.txt
python -m electrodacus_parser.cli convert data/sample_raw_bits.txt
```

For development deps:
```bash
python -m pip install -e .[dev]
```

## CLI usage
Print a hex dump from a capture file (default command):
```bash
electrodacus-parser data/sample_raw_bits.txt
```

Equivalent explicit form:
```bash
electrodacus-parser hexdump data/sample_raw_bits.txt
```

If your ASCII bit files should be packed LSB-first:
```bash
electrodacus-parser --lsb-first data/sample_raw_bits.txt
```

Metadata as JSON (and hexdump unless `--no-hexdump` is set):
```bash
electrodacus-parser hexdump --json data/sample_raw_bits.txt
```

Parse a captured UART log file and print parsed records to stdout:
```bash
electrodacus-parser convert data/sample_raw_bits.txt
```

To print the full payload (no truncation):
```bash
electrodacus-parser convert --full data/sample_raw_bits.txt
```

## Running tests
```bash
pytest
```

## Code formatting (pre-commit)

This project uses pre-commit to enforce code style. Install and run:

```bash
# Install pre-commit hooks
pre-commit install

# Run on all files
pre-commit run --all-files
```

Hooks include:
- **black** - Python code formatting
- **ruff** - Python linting and import sorting
- **hadolint** - Dockerfile linting
- **yamlfmt** - YAML formatting (docker-compose.yml)
- Standard hooks (trailing whitespace, end-of-file fixer, etc.)

## Docker

All Docker files are in the `docker/` folder.

### Quick run using the provided script:

```bash
cd docker
./run.sh convert
./run.sh hexdump
```

### Using docker-compose directly:

```bash
cd docker
docker-compose run --rm parser convert /data/sample_raw_bits.txt
docker-compose run --rm parser hexdump /data/sample_raw_bits.txt
```

### Manual Docker build and run:

```bash
cd docker
docker build -t electrodacus-parser ..
docker run --rm -v "../data:/data:ro" electrodacus-parser convert /data/sample_raw_bits.txt
```

## Capturing SBMS0 data (UART over USB serial)

SBMS0 can output periodic status lines over UART. When connected via USB (micro USB
to USB-A), many systems will enumerate it as a CH340/CH341 USB-serial adapter.

On Linux, a typical workflow is:
```bash
lsusb
dmesg | grep tty
stty -F /dev/ttyUSB0 115200 cs8 -cstopb -parenb
cat -v /dev/ttyUSB0
```

To save to a file:
```bash
cat -v /dev/ttyUSB0 > yourfile.txt
```

You should see “gibberish-looking” ASCII lines similar to:
```text
#$$#%T#TG|H.H<H&H.H.H'H+*?##-##*#####################$@5%N(
```

## Capture file formats supported (initial)
- **Hex text**: whitespace-separated bytes like `4f 6b 41 79 ...` (optional `0x` prefix).
- **ASCII bits**: a text file containing `0` and `1` characters; any whitespace
  is ignored.
- **Binary / raw bytes**: any other file is treated as already being a byte stream (including
  “gibberish-looking” ASCII captures).


## Logic converted from C
- **[convert2.c](https://groups.google.com/g/electrodacus/c/xks0XWsay90?pli=1)**
