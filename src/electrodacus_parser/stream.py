"""Streaming I/O for SBMS0: serial-port reader, decode loop, publishers.

Reading the SBMS0 over USB on Linux is straightforward — the device shows up
as a tty, we configure it to 115200 8N1 raw mode via ``termios``, then read
line by line. ``paho-mqtt`` is imported lazily so the package stays usable
without it.
"""

from __future__ import annotations

import json
import os
import sys
import time
from collections.abc import Iterable, Iterator
from datetime import datetime, timezone
from typing import Any, Protocol

from .parser import Sbms0Record, decode_line

try:
    import termios

    _HAVE_TERMIOS = True
except ImportError:
    _HAVE_TERMIOS = False


_BAUD_MAP: dict[int, int] = {}
if _HAVE_TERMIOS:
    _BAUD_MAP = {
        9600: termios.B9600,
        19200: termios.B19200,
        38400: termios.B38400,
        57600: termios.B57600,
        115200: termios.B115200,
        230400: termios.B230400,
    }


def _configure_tty(fd: int, baud: int) -> None:
    """Put a tty into 8N1 raw mode at ``baud``.

    No-op (silently) if the fd isn't a tty (regular files, pipes, sockets).
    Raises ``ValueError`` for unsupported baud rates and ``OSError`` for
    other tty errors.
    """

    if not _HAVE_TERMIOS:
        raise OSError("termios not available on this platform")

    speed = _BAUD_MAP.get(baud)
    if speed is None:
        raise ValueError(f"Unsupported baud rate: {baud}")

    try:
        attrs = termios.tcgetattr(fd)
    except termios.error:
        return  # not a tty — caller is reading a file or pipe

    iflag, oflag, cflag, lflag, _ispeed, _ospeed, cc = attrs

    iflag &= ~(
        termios.IGNBRK
        | termios.BRKINT
        | termios.PARMRK
        | termios.ISTRIP
        | termios.INLCR
        | termios.IGNCR
        | termios.ICRNL
        | termios.IXON
        | termios.IXOFF
        | termios.IXANY
    )
    oflag &= ~termios.OPOST
    lflag &= ~(
        termios.ECHO
        | termios.ECHONL
        | termios.ICANON
        | termios.ISIG
        | termios.IEXTEN
    )
    cflag &= ~(termios.CSIZE | termios.PARENB | termios.CSTOPB | termios.CRTSCTS)
    cflag |= termios.CS8 | termios.CREAD | termios.CLOCAL

    cc[termios.VMIN] = 1
    cc[termios.VTIME] = 0

    termios.tcsetattr(
        fd, termios.TCSANOW, [iflag, oflag, cflag, lflag, speed, speed, cc]
    )


def open_serial(path: str, *, baud: int = 115200) -> int:
    """Open a serial-style path and configure it for SBMS0 reads."""

    fd = os.open(path, os.O_RDONLY | os.O_NOCTTY)
    try:
        _configure_tty(fd, baud)
    except OSError:
        os.close(fd)
        raise
    return fd


def read_lines(fd: int, *, chunk_size: int = 256) -> Iterator[str]:
    """Yield ASCII lines from ``fd`` until EOF.

    Lines are split on CR or LF; non-ASCII bytes inside a line cause that
    line to be silently dropped.
    """

    buf = bytearray()
    while True:
        chunk = os.read(fd, chunk_size)
        if not chunk:
            return
        for byte in chunk:
            if byte in (0x0A, 0x0D):
                if buf:
                    try:
                        yield buf.decode("ascii")
                    except UnicodeDecodeError:
                        pass
                    buf.clear()
            else:
                buf.append(byte)


def stream_lines_from_path(
    path: str,
    *,
    baud: int = 115200,
    reconnect: bool = True,
    reconnect_delay: float = 2.0,
    log: Any = sys.stderr,
) -> Iterator[str]:
    """Yield lines from a serial path, optionally reopening on EOF/error."""

    while True:
        try:
            fd = open_serial(path, baud=baud)
        except OSError as exc:
            print(f"sbms0: open {path} failed: {exc}", file=log, flush=True)
            if not reconnect:
                return
            time.sleep(reconnect_delay)
            continue

        try:
            yield from read_lines(fd)
        except OSError as exc:
            print(f"sbms0: read from {path} failed: {exc}", file=log, flush=True)
        finally:
            try:
                os.close(fd)
            except OSError:
                pass

        if not reconnect:
            return
        print(
            f"sbms0: {path} closed; reopening in {reconnect_delay:.1f}s",
            file=log,
            flush=True,
        )
        time.sleep(reconnect_delay)


def record_to_jsonable(
    rec: Sbms0Record, *, received_at: str | None = None
) -> dict[str, Any]:
    """Serialize a record to a JSON-safe dict.

    ``received_at`` defaults to the wall-clock time at the moment of the
    call, in ISO-8601 UTC. The ``device_timestamp`` field is the SBMS0's
    own clock as it appears in the frame (year/month/day/hour/min/sec
    fields concatenated), which may not match wall-clock time.
    """

    if received_at is None:
        received_at = (
            datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        )
    return {
        "received_at": received_at,
        "line_no": rec.line_no,
        "device_timestamp": (
            f"{rec.year:02d}-{rec.month:02d}-{rec.day:02d}"
            f"T{rec.hour:02d}:{rec.minute:02d}:{rec.second:02d}"
        ),
        "soc_pct": rec.soc,
        "cells_mv": list(rec.cells_mv),
        "internal_temp_c": rec.it_c,
        "external_temp_c": rec.et_c,
        "battery_ma": rec.batt_ma,
        "pv1_ma": rec.pv1_ma,
        "pv2_ma": rec.pv2_ma,
        "ext_ma": rec.ext_ma,
        "stat": rec.stat,
        "pv_level": rec.pv_level,
        "pvdiv": rec.pvdiv,
        "adc2": rec.adc2,
        "adc3": rec.adc3,
        "dmppt": rec.dmppt,
        "crc_ok": rec.crc_ok,
        "crc_residual": rec.crc_residual,
    }


class Publisher(Protocol):
    def publish(self, payload: dict[str, Any]) -> None: ...

    def close(self) -> None: ...


class StdoutJsonlPublisher:
    """Writes one JSON object per line to stdout, flushed every record."""

    def publish(self, payload: dict[str, Any]) -> None:
        sys.stdout.write(json.dumps(payload) + "\n")
        sys.stdout.flush()

    def close(self) -> None:
        pass


class MqttPublisher:
    """Publishes each record as JSON to an MQTT topic.

    Requires ``paho-mqtt>=2.0`` (install with ``pip install
    'electrodacus-parser[mqtt]'``).
    """

    def __init__(
        self,
        *,
        broker: str,
        port: int = 1883,
        topic: str = "electrodacus/sbms0",
        qos: int = 0,
        username: str | None = None,
        password: str | None = None,
        client_id: str = "electrodacus-parser",
        keepalive: int = 60,
    ) -> None:
        try:
            import paho.mqtt.client as mqtt
            from paho.mqtt.enums import CallbackAPIVersion
        except ImportError as exc:
            raise ImportError(
                "MQTT publishing requires paho-mqtt>=2. "
                "Install with: pip install 'electrodacus-parser[mqtt]'"
            ) from exc

        self._topic = topic
        self._qos = qos
        self._client: Any = mqtt.Client(
            callback_api_version=CallbackAPIVersion.VERSION2,
            client_id=client_id,
        )
        if username is not None:
            self._client.username_pw_set(username, password)
        self._client.connect_async(broker, port, keepalive=keepalive)
        self._client.loop_start()

    def publish(self, payload: dict[str, Any]) -> None:
        self._client.publish(self._topic, json.dumps(payload), qos=self._qos)

    def close(self) -> None:
        self._client.loop_stop()
        try:
            self._client.disconnect()
        except Exception:  # noqa: BLE001 — best-effort cleanup
            pass


def run_stream(
    lines: Iterable[str],
    publishers: list[Publisher],
    *,
    include_errors: bool = False,
    log: Any = sys.stderr,
) -> dict[str, int]:
    """Decode ``lines`` and dispatch each accepted record to ``publishers``.

    Returns a counter dict (``total``, ``published``, ``malformed``,
    ``crc_failures``) when the iterator exhausts. For an infinite serial
    stream this only returns when interrupted.
    """

    stats = {"total": 0, "published": 0, "malformed": 0, "crc_failures": 0}
    line_no = 0
    try:
        for line in lines:
            line_no += 1
            stats["total"] += 1
            rec = decode_line(line, line_no=line_no)
            if rec is None:
                stats["malformed"] += 1
                continue
            if not rec.crc_ok:
                stats["crc_failures"] += 1
                if not include_errors:
                    continue
            payload = record_to_jsonable(rec)
            for pub in publishers:
                try:
                    pub.publish(payload)
                except Exception as exc:  # noqa: BLE001 — keep stream alive
                    print(
                        f"sbms0: publish error ({type(exc).__name__}): {exc}",
                        file=log,
                        flush=True,
                    )
            stats["published"] += 1
    finally:
        for pub in publishers:
            try:
                pub.close()
            except Exception:  # noqa: BLE001
                pass
    return stats
