import shutil
import subprocess
import sys

# Install the cortex package bundled with this submission.
subprocess.check_call(["uv", "pip", "install", "--python", sys.executable, "./packages/cortex"])

# agent/ has a pyproject.toml with setuptools namespace packages (metta.agent, metta.ops),
# so installing it as a path dep gives us the metta.agent namespace without needing the
# full metta package.
subprocess.check_call(["uv", "pip", "install", "--python", sys.executable, "./agent/"])

# setuptools leaves a build/ dir inside agent/ that contains a partial source copy.
# The policy loader adds the extraction root to sys.path, so agent/build/lib/metta/
# would shadow the properly installed package. Remove it.
shutil.rmtree("agent/build", ignore_errors=True)

subprocess.check_call(["uv", "pip", "install", "--python", sys.executable, "torchrl", "safetensors", "optree"])
