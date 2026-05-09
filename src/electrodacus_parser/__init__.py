from importlib.metadata import PackageNotFoundError, version

from .parser import (
    SBMS0_LINE_LEN,
    DecodeStats,
    Sbms0Record,
    decode_line,
    decode_records,
    hex_dump,
    looks_like_sbms0_line,
)
from .stream import (
    MqttPublisher,
    Publisher,
    StdoutJsonlPublisher,
    open_serial,
    read_lines,
    record_to_jsonable,
    run_stream,
    stream_lines_from_path,
)

try:
    __version__ = version("electrodacus-parser")
except PackageNotFoundError:
    __version__ = "0.0.0+unknown"

__all__ = [
    "SBMS0_LINE_LEN",
    "DecodeStats",
    "MqttPublisher",
    "Publisher",
    "Sbms0Record",
    "StdoutJsonlPublisher",
    "__version__",
    "decode_line",
    "decode_records",
    "hex_dump",
    "looks_like_sbms0_line",
    "open_serial",
    "read_lines",
    "record_to_jsonable",
    "run_stream",
    "stream_lines_from_path",
]
