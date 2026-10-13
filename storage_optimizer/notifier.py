"""macOS native notification (Notification Center) — no external account or API key needed."""

import subprocess


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


def notify(title: str, message: str) -> None:
    script = f'display notification "{_escape(message)}" with title "{_escape(title)}"'
    subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=10)
