# electrodacus-parser

Parses Electrodacus SBMS0 USB/UART capture data and decodes battery metrics.

## Features

- Decode SBMS0 UART logs to human-readable battery metrics (SOC, cell voltages, temperatures, currents)
- Hex dump capture files
- Docker support for easy portability

## Project Layout

- **`src/electrodacus_parser/`** - Library code
- **`tests/`** - pytest tests
- **`data/`** - Sample capture files
- **`docker/`** - Docker configuration and run scripts

## Requirements

- Python 3.10+
- Docker (optional)

## Installation

```bash
# Editable install
pip install -e .

# With development dependencies
pip install -e .[dev]
```

## Usage

### Decode SBMS0 UART Log

```bash
electrodacus-parser convert data/sample_raw_bits.txt
```

Output shows battery metrics:
```
idx  line  timestamp           SOC  C1[mV] C2[mV] C3[mV] C4[mV] C5[mV] C6[mV] C7[mV] C8[mV]   IT  ET   Batt[mA]  PV1   PV2   EXT  Stat   CRC
  1     1  00-01-01 00:02:49   49   3365  3378  3392  3370  3378  3378  3371  3375  215 -450        -7     0     0     0  20480  OK
```

### Hex Dump

```bash
electrodacus-parser hexdump data/sample_raw_bits.txt
```

### Docker

Quick run:
```bash
cd docker
./run.sh convert
./run.sh hexdump
```

Or manually:
```bash
cd docker
docker-compose run --rm parser convert /data/sample_raw_bits.txt
```

## Development

### Running Tests

```bash
pytest
```

### Code Formatting

```bash
pre-commit install
pre-commit run --all-files
```

## Capturing SBMS0 Data

Connect via USB (CH340/CH341 serial adapter) and capture:

```bash
stty -F /dev/ttyUSB0 115200 cs8 -cstopb -parenb
cat -v /dev/ttyUSB0 > capture.txt
```

Expected output format:
```
#$$#%T#TG|H.H<H&H.H.H'H+*?##-##*#####################$@5%N(
```

## References

- [convert2.c](https://groups.google.com/g/electrodacus/c/xks0XWsay90?pli=1) - Original C decoder
