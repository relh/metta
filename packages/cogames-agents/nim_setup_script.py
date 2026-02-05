import runpy
import subprocess
import sys
from pathlib import Path

subprocess.check_call(["uv", "pip", "install", "--python", sys.executable, "cogames", "numpy"])

build_module = Path.cwd() / "src" / "cogames_agents" / "policy" / "nim_agents" / "build.py"
mod = runpy.run_path(str(build_module))
mod["build_nim"]()
