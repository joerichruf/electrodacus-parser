from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .parser import Sbms0Record, decode_records, hex_dump
from .stream import (
    MqttPublisher,
    Publisher,
    StdoutJsonlPublisher,
    read_lines,
    run_stream,
    stream_lines_from_path,
)


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

    ap_stream = sub.add_parser(
        "stream",
        help="Continuously decode an SBMS0 stream to stdout JSONL and/or MQTT",
    )
    ap_stream.add_argument(
        "input",
        help="Serial device path (e.g. /dev/ttyUSB0) or '-' to read from stdin",
    )
    ap_stream.add_argument(
        "--baud",
        type=int,
        default=115200,
        help="Baud rate when input is a serial device (default: 115200)",
    )
    ap_stream.add_argument(
        "--include-errors",
        action="store_true",
        help="Publish records whose CRC failed (crc_ok=false in payload)",
    )
    ap_stream.add_argument(
        "--no-stdout",
        action="store_true",
        help="Suppress JSONL on stdout (useful with --mqtt-broker only)",
    )
    ap_stream.add_argument(
        "--once",
        action="store_true",
        help="Read until EOF then exit (default: reopen serial port forever)",
    )
    ap_stream.add_argument(
        "--reconnect-delay",
        type=float,
        default=2.0,
        help="Seconds to wait before reopening a serial port after EOF/error",
    )
    ap_stream.add_argument("--mqtt-broker", help="MQTT broker hostname")
    ap_stream.add_argument("--mqtt-port", type=int, default=1883)
    ap_stream.add_argument("--mqtt-topic", default="electrodacus/sbms0")
    ap_stream.add_argument(
        "--mqtt-qos", type=int, default=0, choices=[0, 1, 2]
    )
    ap_stream.add_argument("--mqtt-username")
    ap_stream.add_argument(
        "--mqtt-password-env",
        default="MQTT_PASSWORD",
        help="Environment variable to read the MQTT password from",
    )
    ap_stream.add_argument("--mqtt-client-id", default="electrodacus-parser")

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


def _cmd_stream(args: argparse.Namespace) -> int:
    publishers: list[Publisher] = []
    if not args.no_stdout:
        publishers.append(StdoutJsonlPublisher())
    if args.mqtt_broker:
        password = (
            os.environ.get(args.mqtt_password_env) if args.mqtt_username else None
        )
        publishers.append(
            MqttPublisher(
                broker=args.mqtt_broker,
                port=args.mqtt_port,
                topic=args.mqtt_topic,
                qos=args.mqtt_qos,
                username=args.mqtt_username,
                password=password,
                client_id=args.mqtt_client_id,
            )
        )

    if not publishers:
        print(
            "sbms0: refusing to run with no publishers (you passed --no-stdout "
            "without --mqtt-broker)",
            file=sys.stderr,
        )
        return 1

    if args.input == "-":
        lines = read_lines(sys.stdin.fileno())
    else:
        lines = stream_lines_from_path(
            args.input,
            baud=args.baud,
            reconnect=not args.once,
            reconnect_delay=args.reconnect_delay,
        )

    try:
        stats = run_stream(lines, publishers, include_errors=args.include_errors)
    except KeyboardInterrupt:
        print("sbms0: interrupted", file=sys.stderr)
        return 0

    print(
        f"sbms0: stream ended — total={stats['total']} published={stats['published']} "
        f"malformed={stats['malformed']} crc_failures={stats['crc_failures']}",
        file=sys.stderr,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = _build_parser()
    args = ap.parse_args(argv)
    if args.cmd == "convert":
        return _cmd_convert(args)
    if args.cmd == "hexdump":
        return _cmd_hexdump(args)
    if args.cmd == "stream":
        return _cmd_stream(args)
    ap.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
