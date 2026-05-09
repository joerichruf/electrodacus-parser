from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .parser import Sbms0Record, decode_records, hex_dump


def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="electrodacus-parser")
    sub = ap.add_subparsers(dest="cmd", required=True)

    ap_convert = sub.add_parser(
        "convert",
        help="Decode SBMS0 UART log and print battery metrics",
    )
    ap_convert.add_argument("input", help="Input log file (e.g. captured from cat -v)")
    ap_convert.add_argument(
        "--include-errors",
        action="store_true",
        help="Include records whose CRC failed (off by default; values cannot be trusted)",
    )
    ap_convert.add_argument(
        "--exit-on-errors",
        action="store_true",
        help="Exit with status 2 if any malformed or CRC-failed lines were seen",
    )

    ap_hex = sub.add_parser("hexdump", help="Print a hex dump of a capture file")
    ap_hex.add_argument("capture", help="Path to capture file (read as raw bytes)")

    return ap


def _print_table(records: list[Sbms0Record]) -> None:
    if not records:
        return

    idx_w = max(3, len(str(len(records))))
    line_w = max(4, len(str(max(r.line_no for r in records))))

    cell_hdr = " ".join(f"C{i}[mV]" for i in range(1, 9))
    header = (
        f"{'idx':>{idx_w}}  {'line':>{line_w}}  timestamp           "
        f"SOC  {cell_hdr}  IT[°C] ET[°C]  Batt[mA]  "
        f"PV1[mA] PV2[mA] EXT[mA]  Stat   PVlvl   CRC"
    )
    print(header)
    print("-" * len(header))

    for i, r in enumerate(records, start=1):
        ts = (
            f"{r.year:02d}-{r.month:02d}-{r.day:02d} "
            f"{r.hour:02d}:{r.minute:02d}:{r.second:02d}"
        )
        cells = " ".join(f"{c:5d}" for c in r.cells_mv)
        crc = "OK" if r.crc_ok else f"ERR({r.crc_residual})"
        print(
            f"{i:>{idx_w}}  {r.line_no:>{line_w}}  {ts}  "
            f"{r.soc:3d}  {cells}  "
            f"{r.it_c:5.1f}  {r.et_c:5.1f}  "
            f"{r.batt_ma:8d}  {r.pv1_ma:6d}  {r.pv2_ma:6d}  {r.ext_ma:6d}  "
            f"{r.stat:5d}  {r.pv_level:3d}    {crc}"
        )


def _cmd_convert(args: argparse.Namespace) -> int:
    text = Path(args.input).read_text(encoding="utf-8", errors="replace")
    records, stats = decode_records(text, require_crc=not args.include_errors)

    _print_table(records)

    summary = (
        f"\n{len(records)} record(s) shown, "
        f"{stats.skipped_malformed} malformed, "
        f"{stats.crc_failures} CRC failure(s), "
        f"{stats.skipped_blank} blank line(s) "
        f"(of {stats.total_lines} total)."
    )
    print(summary, file=sys.stderr)

    if args.exit_on_errors and (stats.skipped_malformed or stats.crc_failures):
        return 2
    return 0


def _cmd_hexdump(args: argparse.Namespace) -> int:
    data = Path(args.capture).read_bytes()
    print(hex_dump(data))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = _build_parser()
    args = ap.parse_args(argv)
    if args.cmd == "convert":
        return _cmd_convert(args)
    if args.cmd == "hexdump":
        return _cmd_hexdump(args)
    ap.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
