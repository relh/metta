"""launchd helper for chatprop daemon install."""

from __future__ import annotations

import sys
from pathlib import Path

LAUNCHD_LABEL = "dev.metta.chatprop"


def build_launchd_plist(config_path: Path) -> str:
    resolved_config = config_path.expanduser().resolve()
    python_exec = Path(sys.executable).resolve()
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
  <dict>
    <key>Label</key>
    <string>{LAUNCHD_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
      <string>{python_exec}</string>
      <string>-m</string>
      <string>chatprop</string>
      <string>daemon</string>
      <string>--config</string>
      <string>{resolved_config}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
  </dict>
</plist>
"""


def install_launchd_plist(config_path: Path) -> Path:
    target = Path.home() / "Library" / "LaunchAgents" / f"{LAUNCHD_LABEL}.plist"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(build_launchd_plist(config_path), encoding="utf-8")
    return target
