"""test_cli_automation.py — Cyber Girlfriend CLI automated test helper

Provides the ``CyberCLI`` class that wraps the CLI subprocess for automated
testing: sending messages, capturing replies, parsing affection values and
ANSI-styled output.

Usage::

    from test_cli_automation import CyberCLI

    cli = CyberCLI()
    cli.start()
    # Drain the welcome message before the first send
    cli.read_until_timeout(timeout=3)

    reply = cli.send_message("你好")
    aff = cli.parse_affection(reply)
    print(f"亲密度: {aff}/100")

    mood_raw = cli.send_message("/mood", wait=5)
    mood_data = cli.parse_mood(mood_raw)
    print(mood_data)

    cli.stop()

Smoke test (run this file directly)::

    python test_cli_automation.py
"""

from __future__ import annotations

import os
import queue
import re
import subprocess
import threading
import time

__all__ = ["CyberCLI"]


_PROJECT_DIR = r"C:\Users\Administrator\Desktop\cyber-girlfriend"


class CyberCLI:
    """Automated CLI test helper for Cyber Girlfriend.

    Wraps ``main.py`` in a ``subprocess.Popen`` with piped stdin/stdout,
    reads output asynchronously via a daemon thread + thread-safe queue,
    and provides helpers to strip ANSI codes, parse affection values, and
    parse structured ``/mood`` output.
    """

    def __init__(self, project_dir: str | None = None) -> None:
        """Initialise the helper (does **not** launch the subprocess).

        Args:
            project_dir: Path to the cyber-girlfriend project root.
                         Defaults to the canonical location.
        """
        self.project_dir = project_dir or _PROJECT_DIR
        self.proc: subprocess.Popen | None = None
        self._output_queue: queue.Queue[str] = queue.Queue()
        self._reader_thread: threading.Thread | None = None
        self._stop_reader = threading.Event()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Launch the CLI as a subprocess with ``PIPE`` stdin/stdout/stderr.

        - Uses ``.venv\\Scripts\\python.exe`` to run ``main.py``
        - Sets ``PYTHONIOENCODING=utf-8`` for proper Unicode support
        - Starts a background daemon thread that reads **newline-terminated**
          output from stdout and enqueues each line
        - Sleeps 2 seconds to let the welcome message and prompt appear
        """
        python_exe = os.path.join(
            self.project_dir, ".venv", "Scripts", "python.exe"
        )
        main_py = os.path.join(self.project_dir, "main.py")

        self.proc = subprocess.Popen(
            [python_exe, main_py],
            cwd=self.project_dir,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )

        # Background reader thread
        self._stop_reader.clear()
        self._reader_thread = threading.Thread(
            target=self._reader_loop, daemon=True
        )
        self._reader_thread.start()

        # Allow the CLI to print welcome text and the first prompt
        time.sleep(2)

    def stop(self) -> None:
        """Gracefully shut down the CLI subprocess.

        Sends ``/quit``, waits up to 5 seconds for a clean exit, then
        force-kills if necessary.
        """
        if self.proc is None:
            return
        self._stop_reader.set()
        try:
            self.proc.stdin.write("/quit\n")
            self.proc.stdin.flush()
        except (BrokenPipeError, OSError):
            pass
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait(timeout=3)
        self.proc = None

    # ------------------------------------------------------------------
    # Read helpers
    # ------------------------------------------------------------------

    def _reader_loop(self) -> None:
        """Background thread: read lines from stdout and enqueue them.

        Runs until ``_stop_reader`` is set or the pipe is closed.
        """
        while not self._stop_reader.is_set() and self.proc is not None:
            try:
                line = self.proc.stdout.readline()
                if not line:
                    break
                self._output_queue.put(line)
            except (ValueError, OSError, AttributeError):
                break

    def read_until_timeout(self, timeout: float = 10.0) -> str:
        """Read all available output until no more data for 0.5 seconds.

        Uses a simple polling loop with ``queue.get(timeout=0.1)`` so it
        works correctly on **Windows** (where ``select.select`` cannot be
        used on pipes).

        Args:
            timeout: Maximum total wall-clock time to spend reading.

        Returns:
            The concatenated output with ANSI escape codes stripped.
        """
        end = time.time() + timeout
        lines: list[str] = []
        idle_start: float | None = None

        while time.time() < end:
            try:
                line = self._output_queue.get(timeout=0.1)
                lines.append(line)
                idle_start = None  # data arrived → reset idle timer
            except queue.Empty:
                if idle_start is None:
                    idle_start = time.time()
                elif time.time() - idle_start >= 0.5:
                    break  # no new data for 0.5 s → assume output is complete

        return self._strip_ansi("".join(lines))

    def send_message(self, msg: str, wait: float = 8.0) -> str:
        """Send a message to the CLI and capture the AI reply.

        Writes *msg* to stdin, flushes, waits *wait* seconds for the AI to
        finish responding (streaming ends, affection line printed, prompt
        shown), then reads all available output.

        Args:
            msg: The user message to send.
            wait: How many seconds to wait for the AI response.

        Returns:
            Cleaned text (ANSI codes removed) that was emitted by the CLI
            during the wait period.  Typically includes the AI's name line,
            reply body, affection line, and the next prompt.
        """
        self.proc.stdin.write(msg + "\n")
        self.proc.stdin.flush()
        return self.read_until_timeout(timeout=wait)

    # ------------------------------------------------------------------
    # Parsing helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _strip_ansi(text: str) -> str:
        """Remove ANSI / ECMA-48 escape sequences from *text*."""
        return re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", text)

    def parse_affection(self, text: str) -> int | None:
        """Extract the numeric affection value from text.

        Looks for a pattern like ``💕 亲密度 85/100`` (or the other emoji
        variants such as ``💗``, ``💛``, ``🤍``).

        Returns:
            The integer value (0–100) or ``None`` if no affection line was
            found in *text*.
        """
        m = re.search(r"亲密度\s*(\d+)/100", text)
        return int(m.group(1)) if m else None

    def parse_mood(self, text: str) -> dict | None:
        """Parse ``/mood`` command output into a structured dictionary.

        Example input::

            🎭 情绪状态
              😊 Mood：happy（强度 75%）
              ⚡ 精力：██████░░░░ 60%
              📊 效价 +0.50 / 唤醒 0.60
              ...

        Returns:
            A dict with some or all of the keys ``mood`` (str),
            ``intensity`` (float 0–1), ``energy`` (float 0–1),
            ``valence`` (float), ``arousal`` (float); or ``None`` if no
            mood data was detected.
        """
        result: dict[str, str | float] = {}

        # Mood name and intensity
        mood_m = re.search(r"Mood[：:]\s*(\w+)\s*（?强度\s*([\d.]+)%", text)
        if mood_m:
            result["mood"] = mood_m.group(1)
            result["intensity"] = float(mood_m.group(2)) / 100.0

        # Energy (the bar contains Unicode block chars)
        energy_m = re.search(r"精力[：:].*?([\d.]+)%", text)
        if energy_m:
            result["energy"] = float(energy_m.group(1)) / 100.0

        # Valence / Arousal
        va_m = re.search(
            r"效价\s*([+-]?\d+(?:\.\d+)?)\s*/\s*唤醒\s*(\d+(?:\.\d+)?)",
            text,
        )
        if va_m:
            result["valence"] = float(va_m.group(1))
            result["arousal"] = float(va_m.group(2))

        return result if result else None


# ------------------------------------------------------------------
# Smoke test
# ------------------------------------------------------------------

def _smoke_test() -> int:
    """Run a quick integration check against the real CLI.

    Returns 0 on success, 1 on failure.
    """
    print("=" * 50)
    print("  CyberCLI smoke test")
    print("=" * 50)

    cli = CyberCLI()
    failures = 0

    try:
        # --- Start ---
        print("\n[1/5] Starting CLI...")
        cli.start()
        print("  ✓ CLI process launched")

        # --- Drain welcome ---
        print("[2/5] Draining welcome message...")
        welcome = cli.read_until_timeout(timeout=3)
        if welcome:
            # Just show a preview
            preview = welcome.strip().replace("\n", "\\n")[:120]
            print(f"  ✓ Welcome received ({len(welcome)} chars): {preview}")
        else:
            # Not necessarily a failure — the welcome may have been dropped
            print("  ⚠ No welcome output (may be empty)")

        # --- Send a message ---
        print("[3/5] Sending '你好'...")
        reply = cli.send_message("你好", wait=10)
        if reply.strip():
            # Show truncated preview
            preview = reply.strip().replace("\n", "\\n")[:200]
            print(f"  ✓ Reply received ({len(reply)} chars): {preview}")
        else:
            print("  ✗ Empty reply")
            failures += 1

        # --- Parse affection ---
        print("[4/5] Parsing affection...")
        aff = cli.parse_affection(reply)
        if aff is not None:
            print(f"  ✓ Affection: {aff}/100")
        else:
            # The reply might not contain an affection line if no LLM connected
            print("  ⚠ No affection value found (no LLM / setup needed?)")

        # --- /mood ---
        print("[5/5] Sending '/mood'...")
        mood_raw = cli.send_message("/mood", wait=5)
        mood_data = cli.parse_mood(mood_raw)
        if mood_data:
            print(f"  ✓ Mood data: {mood_data}")
        else:
            # Mood engine may not be active without an LLM
            print("  ⚠ No mood data parsed (engine may be inactive)")

    except Exception as exc:
        print(f"\n  ✗ Unexpected error: {exc}")
        failures += 1
    finally:
        cli.stop()
        print("\n  CLI stopped.")

    print("\n" + ("-" * 50))
    if failures:
        print(f"  FAILED – {failures} error(s)")
    else:
        print("  PASSED (with possible ⚠ warnings)")
    print("-" * 50)
    return 1 if failures else 0


if __name__ == "__main__":
    import sys

    sys.exit(_smoke_test())
