from fastapi import APIRouter

from metta.app_backend.state_page.router import create_state_page_router as _create_state_page_router


def create_state_page_router() -> APIRouter:
    return _create_state_page_router()
