"""Perf profiler that runs as a child process.

This module provides a way to profile a process using Linux perf while keeping
perf as a child process. This limits blast radius: if perf fails to start or
crashes, the profiled workload continues unaffected.

Usage:
    profiler = PerfProfiler(pid=target_pid, data_path="/tmp/perf.data")
    profiler.start()
    # ... target process does work ...
    profiler.stop()
"""

import glob
import logging
import re
import shutil
import signal
import subprocess
import time
from pathlib import Path

logger = logging.getLogger(__name__)


class PerfProfiler:
    """Profile a process using Linux perf, running perf as a child process."""

    def __init__(
        self,
        pid: int,
        data_path: str | Path,
        log_path: str | Path | None = None,
        frequency: int = 99,
    ):
        """Initialize the profiler.

        Args:
            pid: Process ID to profile.
            data_path: Path where perf.data will be written.
            log_path: Optional path for perf's log output. If None, messages go to stderr.
            frequency: Sampling frequency in Hz (default 99 to avoid lockstep).
        """
        self.pid = pid
        self.data_path = Path(data_path)
        self.log_path = Path(log_path) if log_path else None
        self.frequency = frequency
        self._proc: subprocess.Popen | None = None
        self._file_handler: logging.FileHandler | None = None

    def start(self) -> bool:
        """Start profiling. Returns True if perf started successfully."""
        perf_bin = _find_perf_binary()

        # Add file handler if log_path specified
        if self.log_path:
            try:
                self._file_handler = logging.FileHandler(self.log_path)
                self._file_handler.setFormatter(logging.Formatter("%(message)s"))
                self._file_handler.setLevel(logging.DEBUG)
                logger.addHandler(self._file_handler)
                # Ensure logger level allows our messages through
                if logger.level == logging.NOTSET or logger.level > logging.INFO:
                    logger.setLevel(logging.INFO)
            except OSError as e:
                logger.warning(f"Failed to open perf log file {self.log_path}: {e}")

        try:
            self._proc = subprocess.Popen(
                [
                    perf_bin,
                    "record",
                    f"--freq={self.frequency}",
                    "--call-graph=fp",  # Collect stack traces via frame pointers
                    "--clockid=CLOCK_MONOTONIC",
                    f"--pid={self.pid}",
                    f"--output={self.data_path}",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )

            # Wait for perf to attach by polling for data file creation or process exit
            deadline = time.monotonic() + 5.0
            while time.monotonic() < deadline:
                if self._proc.poll() is not None:
                    # Process exited - failed to start
                    stderr = self._proc.stderr.read().decode() if self._proc.stderr else ""
                    logger.warning(f"perf failed to start: {stderr}")
                    self._proc = None
                    return False
                if self.data_path.exists():
                    # Data file created - perf is recording
                    break
                time.sleep(0.01)
            else:
                # Timed out waiting for perf to start
                logger.warning("perf timed out waiting to attach")
                self._proc.kill()
                self._proc = None
                return False

            logger.info(f"perf profiler started (pid={self._proc.pid}, binary={perf_bin}), profiling pid={self.pid}")
            return True

        except FileNotFoundError:
            logger.info("perf not installed, continuing without profiling")
            return False
        except Exception as e:
            logger.warning(f"Failed to start perf: {e}")
            return False

    def stop(self) -> None:
        """Stop profiling gracefully."""
        if self._proc is None:
            return

        stop_signal = signal.SIGINT
        self._proc.send_signal(stop_signal)
        try:
            self._proc.wait(timeout=5)
            if self._proc.returncode == -stop_signal:
                logger.info(f"perf stopped, data written to {self.data_path}")
            else:
                # Capture any error output
                stderr = self._proc.stderr.read().decode() if self._proc.stderr else ""
                logger.warning(f"perf exited with code {self._proc.returncode}")
                if stderr:
                    logger.warning(f"perf stderr: {stderr}")
        except subprocess.TimeoutExpired:
            self._proc.kill()
            logger.warning("perf killed after timeout")

        self._proc = None

        # Copy Python's perf map file if it exists (generated when PYTHONPERFSUPPORT=1)
        perf_map = Path(f"/tmp/perf-{self.pid}.map")
        if perf_map.exists():
            dest = self.data_path.parent / perf_map.name
            try:
                shutil.copy(perf_map, dest)
                logger.info(f"Copied {perf_map} to {dest}")
            except shutil.SameFileError:
                logger.info(f"Perf map already at {dest}")
            except Exception as e:
                logger.warning(f"Failed to copy perf map {perf_map} to {dest}: {e}")

        if self._file_handler:
            logger.removeHandler(self._file_handler)
            self._file_handler.close()
            self._file_handler = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
        return False


def _parse_version(path: str) -> tuple[int, ...]:
    """Extract version tuple from a path like /usr/lib/linux-tools-5.15.0-164/perf."""
    match = re.search(r"linux-tools-(\d+)\.(\d+)\.(\d+)-(\d+)", path)
    if match:
        return tuple(int(x) for x in match.groups())
    return (0, 0, 0, 0)


def _find_perf_binary() -> str:
    """Find a working perf binary, bypassing the kernel version check wrapper.

    On Ubuntu, /usr/bin/perf is a wrapper script that checks if the running
    kernel version matches the installed linux-tools package. In containers,
    this often fails because the host kernel differs from the container's
    installed tools. We look for the actual binary in /usr/lib/linux-tools-*/perf
    and use it directly, which works across kernel versions for most use cases.
    """
    # Look for perf binaries in linux-tools directories (Ubuntu layout)
    candidates = glob.glob("/usr/lib/linux-tools-*/perf")
    if candidates:
        # Sort by parsed version number to get the most recent
        candidates.sort(key=_parse_version)
        return candidates[-1]

    # Fall back to PATH lookup (may hit the wrapper script on Ubuntu)
    return "perf"
