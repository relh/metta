import uvicorn

from dashboard.backend.dashboard_backend.app import app
from dashboard.backend.dashboard_backend.config import settings

if __name__ == "__main__":
    uvicorn.run(app, host=settings.DASHBOARD_HOST, port=settings.DASHBOARD_PORT)
