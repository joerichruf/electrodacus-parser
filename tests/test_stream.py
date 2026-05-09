import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from electrodacus_parser import (
    Publisher,
    decode_line,
    read_lines,
    record_to_jsonable,
    run_stream,
)

REPO = Path(__file__).resolve().parents[1]
SAMPLE = REPO / "data" / "sample_raw_bits.txt"


class _CapturingPublisher:
    def __init__(self) -> None:
        self.payloads: list[dict[str, Any]] = []
        self.closed = False

    def publish(self, payload: dict[str, Any]) -> None:
        self.payloads.append(payload)

    def close(self) -> None:
        self.closed = True


def test_record_to_jsonable_has_expected_keys():
    line = SAMPLE.read_text().splitlines()[0]
    rec = decode_line(line, line_no=1)
    assert rec is not None
    payload = record_to_jsonable(rec, received_at="2026-01-01T00:00:00Z")

    assert payload["received_at"] == "2026-01-01T00:00:00Z"
    assert payload["soc_pct"] == 49
    assert payload["cells_mv"] == [3365, 3378, 3392, 3370, 3378, 3378, 3371, 3375]
    assert payload["internal_temp_c"] == 21.5
    assert payload["external_temp_c"] == -45.0
    assert payload["battery_ma"] == -7
    assert payload["crc_ok"] is True
    assert payload["crc_residual"] == 0
    assert payload["device_timestamp"] == "00-01-01T00:02:49"

    json.dumps(payload)


def test_record_to_jsonable_default_received_at_is_iso_zulu():
    rec = decode_line(SAMPLE.read_text().splitlines()[0], line_no=1)
    assert rec is not None
    payload = record_to_jsonable(rec)
    assert payload["received_at"].endswith("Z")
    assert "T" in payload["received_at"]


def test_run_stream_publishes_only_crc_ok_by_default():
    pub = _CapturingPublisher()
    stats = run_stream(SAMPLE.read_text().splitlines(), [pub])

    assert stats["total"] == 6
    assert stats["published"] == 5
    assert stats["crc_failures"] == 1
    assert stats["malformed"] == 0
    assert all(p["crc_ok"] for p in pub.payloads)
    assert pub.closed is True


def test_run_stream_publishes_crc_failures_when_enabled():
    pub = _CapturingPublisher()
    stats = run_stream(
        SAMPLE.read_text().splitlines(), [pub], include_errors=True
    )

    assert stats["total"] == 6
    assert stats["published"] == 6
    assert sum(1 for p in pub.payloads if not p["crc_ok"]) == 1


def test_run_stream_keeps_going_when_a_publisher_raises():
    class Flaky:
        def __init__(self) -> None:
            self.calls = 0

        def publish(self, payload: dict[str, Any]) -> None:
            self.calls += 1
            if self.calls == 2:
                raise RuntimeError("simulated broker hiccup")

        def close(self) -> None:
            pass

    flaky = Flaky()
    good = _CapturingPublisher()
    stats = run_stream(SAMPLE.read_text().splitlines(), [flaky, good])

    assert stats["published"] == 5
    assert len(good.payloads) == 5  # nothing was dropped on the good publisher


def test_read_lines_splits_on_cr_lf_from_pipe():
    r, w = os.pipe()
    try:
        os.write(w, b"line one\nline two\r\nline three\n")
        os.close(w)
        w = -1
        lines = list(read_lines(r))
    finally:
        os.close(r)
        if w != -1:
            os.close(w)

    assert lines == ["line one", "line two", "line three"]


def test_read_lines_drops_non_ascii_lines():
    r, w = os.pipe()
    try:
        os.write(w, b"good\n\xff\xfe\nstill good\n")
        os.close(w)
        w = -1
        lines = list(read_lines(r))
    finally:
        os.close(r)
        if w != -1:
            os.close(w)

    assert lines == ["good", "still good"]


def test_publisher_protocol_accepts_capturing_publisher():
    pub: Publisher = _CapturingPublisher()
    pub.publish({"hello": "world"})
    pub.close()


@pytest.mark.skipif(
    "ELECTRODACUS_SKIP_INTEGRATION" in os.environ,
    reason="integration tests disabled",
)
def test_cli_stream_from_stdin_emits_jsonl():
    proc = subprocess.run(
        [sys.executable, "-m", "electrodacus_parser.cli", "stream", "-"],
        input=SAMPLE.read_bytes(),
        capture_output=True,
        timeout=10,
    )
    assert proc.returncode == 0, proc.stderr.decode()

    payloads = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
    assert len(payloads) == 5
    assert payloads[0]["soc_pct"] == 49
    assert payloads[0]["cells_mv"][0] == 3365
    assert all(p["crc_ok"] for p in payloads)


@pytest.mark.skipif(
    "ELECTRODACUS_SKIP_INTEGRATION" in os.environ,
    reason="integration tests disabled",
)
def test_cli_stream_include_errors_emits_all_six():
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "electrodacus_parser.cli",
            "stream",
            "-",
            "--include-errors",
        ],
        input=SAMPLE.read_bytes(),
        capture_output=True,
        timeout=10,
    )
    assert proc.returncode == 0, proc.stderr.decode()
    payloads = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
    assert len(payloads) == 6
    assert sum(1 for p in payloads if not p["crc_ok"]) == 1


def test_cli_stream_refuses_when_no_publishers():
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "electrodacus_parser.cli",
            "stream",
            "-",
            "--no-stdout",
        ],
        input=b"",
        capture_output=True,
        timeout=5,
    )
    assert proc.returncode == 1
    assert b"refusing to run" in proc.stderr
