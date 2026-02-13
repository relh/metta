import typing

from fastapi import FastAPI
from fastapi.params import Depends
from fastapi.routing import APIRoute

from metta.app_backend.auth import _no_auth, get_softmax_user_or_raise, get_user, get_user_or_raise

AUTH_DEPENDENCIES = {get_user, get_user_or_raise, get_softmax_user_or_raise, _no_auth}

FRAMEWORK_PATHS = {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}


def _has_auth_param(endpoint: object) -> bool:
    hints = typing.get_type_hints(endpoint, include_extras=True)
    for name, hint in hints.items():
        if name == "return":
            continue
        for arg in typing.get_args(hint):
            if isinstance(arg, Depends) and arg.dependency in AUTH_DEPENDENCIES:
                return True
    return False


def _collect_routes(app: FastAPI) -> list[tuple[str, str, object]]:
    routes: list[tuple[str, str, object]] = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if route.path in FRAMEWORK_PATHS:
            continue
        for method in route.methods or []:
            routes.append((method, route.path, route.endpoint))
    return routes


def test_all_routes_have_auth(test_app: FastAPI) -> None:
    missing: list[str] = []
    for method, path, endpoint in _collect_routes(test_app):
        if not _has_auth_param(endpoint):
            name = getattr(endpoint, "__name__", repr(endpoint))
            missing.append(f"{method} {path} ({name})")

    assert not missing, (
        "Routes without auth dependency — add ExternalUser/SoftmaxUser/MaybeAuthenticatedUser "
        "or opt out with NoAuthRequired:\n" + "\n".join(f"  {r}" for r in missing)
    )
