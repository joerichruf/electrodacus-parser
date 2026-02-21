from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from .parser import (
    hex_dump,
    iter_sbms0_decoded_records,
    iter_sbms0_uart_records,
    load_capture,
    normalize_to_bytes,
)


def main() -> int:
    ap = argparse.ArgumentParser(prog="electrodacus-parser")
    sub = ap.add_subparsers(dest="cmd")

    ap_hexdump = sub.add_parser("hexdump", help="Normalize capture and print hex dump")
    ap_hexdump.add_argument("capture", help="Path to raw capture file")
    ap_hexdump.add_argument(
        "--lsb-first",
        action="store_true",
        help="When packing ASCII bits, interpret the first bit as LSB (default: MSB)",
    )
    ap_hexdump.add_argument(
        "--json",
        action="store_true",
        help="Output capture metadata as JSON (still prints hex dump unless --no-hexdump)",
    )
    ap_hexdump.add_argument(
        "--no-hexdump",
        action="store_true",
        help="Do not print a hex dump of the normalized byte stream",
    )

    ap_convert = sub.add_parser(
        "convert",
        help="Decode SBMS0 UART text log and print battery metrics",
    )
    ap_convert.add_argument("input", help="Input log file (e.g. captured from cat -v)")
    ap_convert.add_argument(
        "--full",
        action="store_true",
        help="Print full payload (default truncates payload for readability)",
    )
    ap_convert.add_argument(
        "--debug",
        action="store_true",
        help="Print debug information (useful if you suspect output is being suppressed)",
    )

    argv = sys.argv[1:]
    # Backward compatibility: if no explicit subcommand is provided, default to `hexdump`.
    if argv and argv[0] not in {"hexdump", "convert", "-h", "--help"}:
        argv = ["hexdump", *argv]

    args = ap.parse_args(argv)
    cmd = args.cmd

    if cmd == "convert":
        in_path = Path(args.input)
        text = in_path.read_text(encoding="utf-8", errors="replace")
        decoded = iter_sbms0_decoded_records(text)
        raw_records = iter_sbms0_uart_records(text)

        if args.debug:
            print(f"decoded_records={len(decoded)} raw_records={len(raw_records)}")

        def trunc(s: str, n: int) -> str:
            if len(s) <= n:
                return s
            return s[: max(0, n - 1)] + "…"

        if decoded:
            idx_w = max(3, len(str(len(decoded))))
            line_w = max(4, len(str(max((r.line_no for r in decoded), default=0))))

            cell_hdr = " ".join([f"C{i}[mV]" for i in range(1, 9)])
            print(
                f"{'idx':>{idx_w}}  {'line':>{line_w}}  timestamp           SOC  {cell_hdr}   IT  ET   Batt[mA]  PV1   PV2   EXT  Stat   CRC"
            )
            print("-" * 140)

            for i, r in enumerate(decoded, start=1):
                ts = f"{r.year:02d}-{r.month:02d}-{r.day:02d} {r.hour:02d}:{r.minute:02d}:{r.second:02d}"
                cells = " ".join(f"{c:5d}" for c in r.cells_mv)
                crc_s = "OK" if r.crc_ok else f"ERR({r.crc})"
                print(
                    f"{i:>{idx_w}}  {r.line_no:>{line_w}}  {ts}  {r.soc:3d}  {cells}  {r.it_c:3d} {r.et_c:3d}"
                    f"  {r.batt_ma:8d}  {r.pv1_ma:4d}  {r.pv2_ma:4d}  {r.ext_ma:4d}  {r.stat:5d}  {crc_s}"
                )
        else:
            # Fallback to showing the raw record structure.
            idx_w = max(3, len(str(len(raw_records))))
            line_w = max(4, len(str(max((r.line_no for r in raw_records), default=0))))
            print(f"{'idx':>{idx_w}}  {'line':>{line_w}}  seq  {'tail':<8}  payload")
            print("-" * 80)
            for i, r in enumerate(raw_records, start=1):
                tail = r.tail_marker or ""
                payload = r.payload if args.full else trunc(r.payload, 72)
                print(
                    f"{i:>{idx_w}}  {r.line_no:>{line_w}}  {(r.seq or ''):>3}  {tail:<8}  {payload}"
                )
        return 0

    if cmd == "hexdump":
        capture = load_capture(args.capture)
        normalized = normalize_to_bytes(capture, msb_first=not args.lsb_first)

        if args.json:
            meta = asdict(capture)
            meta["source_path"] = str(capture.source_path)
            meta["source_size"] = len(capture.data)
            meta["normalized_size"] = len(normalized)
            print(json.dumps(meta, indent=2))

        if not args.no_hexdump:
            print(hex_dump(normalized))
        return 0

    ap.error(f"unknown command: {cmd}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
