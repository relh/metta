"""
Constants used by runners, originally from common/src/metta/common/util/constants.py
Redefined here for safer use within containerized environments that do not copy
the entire project's folder structure.
"""

DEV_STATS_SERVER_URI = "http://localhost:8000"
LOCAL_MACHINE_TOKEN = "local-dev-user@example.com"
METTA_WANDB_PROJECT = "metta"
METTA_WANDB_ENTITY = "metta-research"
OBSERVATORY_AUTH_SERVER_URL = "https://softmax.com/api"
PROD_STATS_SERVER_URI = "https://api.observatory.softmax-research.net"
