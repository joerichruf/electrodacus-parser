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

try:
    __version__ = version("electrodacus-parser")
except PackageNotFoundError:
    __version__ = "0.0.0+unknown"

__all__ = [
    "SBMS0_LINE_LEN",
    "DecodeStats",
    "Sbms0Record",
    "__version__",
    "decode_line",
    "decode_records",
    "hex_dump",
    "looks_like_sbms0_line",
]
