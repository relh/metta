"""Public API docs and OpenAPI spec generation.

Two OpenAPI specs are served:

- **Public** (`app.openapi()`, used by softmax.com) — only endpoints on routers decorated with
  `@public_api`, minus any individual endpoints decorated with `@exclude_from_public_docs`.
- **Internal** (`get_openapi(routes=app.routes)`, used by Observatory) — all endpoints, always.

How visibility is determined:

1. `@public_api` on a router factory marks that router's tag as public. All endpoints on public
   routers appear in the public spec by default.
2. `@exclude_from_public_docs` on an individual endpoint removes it from the public spec even if
   its router is public. Use this for softmax-only endpoints that live on otherwise-public routers.
3. Endpoints on non-public routers never appear in the public spec regardless of auth type.
4. The internal spec always includes every endpoint. Never use FastAPI's `include_in_schema=False`
   — it hides endpoints from both specs.

Auth types (ExternalUser, SoftmaxUser, etc.) are enforced at runtime and are independent of
spec visibility. A SoftmaxUser endpoint on a @public_api router will appear in the public
docs; external callers will simply get 403.
"""

import copy
from collections.abc import Callable
from functools import wraps

from fastapi import APIRouter
from fastapi.openapi.utils import get_openapi
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.routing import APIRoute

from metta.app_backend.auth import SoftmaxUser

HTTP_METHODS = {"get", "post", "put", "patch", "delete", "options", "head", "trace"}


def public_api[T: Callable[..., APIRouter]](fn: T) -> T:
    @wraps(fn)
    def wrapper(*args, **kwargs):
        router = fn(*args, **kwargs)
        router._public = True  # type: ignore[attr-defined]
        return router

    return wrapper  # type: ignore[return-value]


def exclude_from_public_docs[T: Callable](fn: T) -> T:
    fn._exclude_from_public_docs = True  # type: ignore[attr-defined]
    return fn


def collect_public_tags(routers: list[APIRouter]) -> set[str]:
    tags: set[str] = set()
    for router in routers:
        if getattr(router, "_public", False):
            tags.update(str(t) for t in router.tags)
    return tags


def _collect_excluded_paths(app: object) -> set[tuple[str, str]]:
    excluded: set[tuple[str, str]] = set()
    for route in getattr(app, "routes", []):
        if isinstance(route, APIRoute) and getattr(route.endpoint, "_exclude_from_public_docs", False):
            for method in route.methods or []:
                excluded.add((route.path, method.lower()))
    return excluded


def _collect_refs(obj: object) -> set[str]:
    refs: set[str] = set()
    if isinstance(obj, dict):
        if "$ref" in obj:
            refs.add(obj["$ref"])
        for v in obj.values():
            refs.update(_collect_refs(v))
    elif isinstance(obj, list):
        for item in obj:
            refs.update(_collect_refs(item))
    return refs


def _reachable_schemas(schema: dict) -> set[str]:
    refs = _collect_refs(schema.get("paths", {}))
    schemas = schema.get("components", {}).get("schemas", {})
    resolved: set[str] = set()
    prefix = "#/components/schemas/"
    queue = [r for r in refs if r.startswith(prefix)]
    while queue:
        ref = queue.pop()
        name = ref[len(prefix) :]
        if name in resolved:
            continue
        resolved.add(name)
        if name in schemas:
            for child in _collect_refs(schemas[name]):
                if child.startswith(prefix):
                    queue.append(child)
    return resolved


def _public_openapi(full_schema: dict, public_tags: set[str], excluded_paths: set[tuple[str, str]]) -> dict:
    schema = copy.deepcopy(full_schema)
    filtered_paths: dict = {}
    for path, operations in schema.get("paths", {}).items():
        filtered_operations: dict = {}
        for method, detail in operations.items():
            if method in HTTP_METHODS:
                if (path, method) in excluded_paths:
                    continue
                tags = detail.get("tags", [])
                if tags and any(t in public_tags for t in tags):
                    filtered_operations[method] = detail
            else:
                filtered_operations[method] = detail
        if filtered_operations:
            filtered_paths[path] = filtered_operations
    schema["paths"] = filtered_paths
    if "tags" in schema:
        schema["tags"] = [t for t in schema["tags"] if t.get("name") in public_tags]
    reachable = _reachable_schemas(schema)
    if "components" in schema and "schemas" in schema["components"]:
        schema["components"]["schemas"] = {k: v for k, v in schema["components"]["schemas"].items() if k in reachable}
    return schema


def create_docs_router(app, public_tags: set[str]) -> APIRouter:
    router = APIRouter(tags=["docs"])

    _full_schema: dict | None = None
    _public_schema: dict | None = None

    def public_openapi() -> dict:
        nonlocal _full_schema, _public_schema
        if _public_schema is None:
            _full_schema = get_openapi(
                title=app.title,
                version=app.version,
                routes=app.routes,
            )
            excluded_paths = _collect_excluded_paths(app)
            _public_schema = _public_openapi(_full_schema, public_tags, excluded_paths)
        return _public_schema

    app.openapi = public_openapi  # type: ignore[method-assign]

    @router.get("/internal/openapi.json")
    async def internal_openapi(_user: SoftmaxUser) -> JSONResponse:
        if _full_schema is None:
            public_openapi()
        return JSONResponse(_full_schema)

    @router.get("/internal/docs")
    async def internal_docs(_user: SoftmaxUser) -> HTMLResponse:
        return HTMLResponse("""
        <!DOCTYPE html>
        <html><head>
        <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist/swagger-ui.css">
        </head><body>
        <div id="swagger-ui"></div>
        <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist/swagger-ui-bundle.js"></script>
        <script>SwaggerUIBundle({url: "/internal/openapi.json", dom_id: "#swagger-ui"})</script>
        </body></html>
        """)

    return router
