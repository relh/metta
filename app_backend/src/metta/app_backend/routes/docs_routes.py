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

from metta.app_backend.auth import NoAuthRequired, SoftmaxUser

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

    @router.get("/docs")
    async def public_docs(_user: NoAuthRequired) -> HTMLResponse:
        return _swagger_html("openapi.json")

    @router.get("/internal/openapi.json")
    async def internal_openapi(_user: SoftmaxUser) -> JSONResponse:
        if _full_schema is None:
            public_openapi()
        return JSONResponse(_full_schema)

    @router.get("/internal/docs")
    async def internal_docs(_user: SoftmaxUser) -> HTMLResponse:
        return _swagger_html("openapi.json")

    return router


_FAVICON_B64 = (
    "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"
)

_LOGO_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 529.22 537.47" height="36">'
    "<defs><style>"
    ".n{fill:#0e2758;stroke-width:0}.l{fill:#bbccf3;stroke-width:0}.s{fill:#859ebe;stroke-width:0}"
    "</style></defs>"
    '<path class="n" d="M435.79,167.09c1.39,14.72,2.28,35.15.07,59.18-2.76,30-8.41,91.42-53.06'
    ",144.85-12.71,15.21-31.5,37.17-64.27,50.75-20.1,8.33-39.72,11.14-57.08,11.14-27.21,0-48.87"
    "-6.89-58.14-10.18-24.28-8.71-46.26-13.88-64.82-17.03-9.81-1.67-17.2-2.89-27.51-3.37-5.3"
    "-.24-11.2-.58-17.52-.58-14.97,0-32.31,1.91-49.66,11.55-7.2,4-22.36,11.82-33.28,28.4-2.31"
    ",3.5-5.73,7.26-7.1,13.17-.77,3.33-.83,6.45-.55,9.17,10.18,16.5,31.9,25.1,70.31,39.79,40.58"
    ",15.52,76.46,23.08,103.36,27.2,39.62,6.07,70.21,6.29,88.85,6.35.69,0,1.39,0,2.08,0,51.31"
    ",0,88.85-5.96,96.74-7.26,21.15-3.46,50.65-8.45,86.8-22.39,39.52-15.24,66.61-25.68,76.25"
    "-50.69,1.5-3.88,4.63-13.43-2.86-55.07-7.57-42.15-18.12-73.19-19.67-77.68-20.91-60.73-31.37"
    '-91.09-47.15-120.59-7.16-13.38-14.37-25.43-21.82-36.72"/>'
    '<path class="s" d="M405.8,126.38c-2.7,14.13-7.43,33.47-16.19,55.39-9.33,23.33-17.43,43.59'
    "-36.11,63.7-9.73,10.47-34.11,36.7-70.49,40.89-3.28.38-6.47.55-9.6.55-15.24,0-29.13-4.16"
    "-46.48-9.36-22.64-6.78-33.98-14.37-61.63-19.18-10.17-1.77-16.26-2.83-24.53-2.83h-.34s-62.3"
    ".23-108.91,65.12c-.28.39-.55.77-.55.77-7.32,10.87-11.91,20.88-14.86,28.78-2.55,6.79-3.97"
    ",12.26-5.54,18.27-1.6,6.15-2.79,11.62-6.31,31.17-1.14,6.36-2.61,14.59-4.27,24.25,6.4-10.91"
    ",17.12-25.9,34.2-39.3,14.59-11.45,27.98-17.13,33.06-19.16,2.85-1.13,13.75-5.35,28.95-7.8"
    ",3.93-.63,12.18-1.8,23.2-1.8,8.13,0,17.77.63,28.3,2.58,6.67,1.23,16.61,3.13,28.41,8.15"
    ",4.01,1.7,11.21,5.03,18.85,9,4.92,2.56,8.37,4.53,14.18,7.14,4.9,2.21,9.03,3.76,11.78,4.74"
    ",0,0,19.23,6.36,40.24,6.98.99.03,1.96.04,2.91.04,5.34,0,9.68-.39,9.68-.39,6.6-.26,15.9"
    "-1.18,26.55-4.2,39.25-11.14,61.44-41.03,74.07-58.02,49.95-67.19,47.93-167.85,47.41-184.77"
    '-5.17-7.02-10.49-13.86-16.02-20.7"/>'
    '<path class="l" d="M263.85,0c-.17,0-.33,0-.49,0-9.56.13-18.97,3.98-51.45,33.34-34.1,30.83'
    "-48.96,48.06-48.96,48.06-45.84,53.13-68.77,79.69-92.48,121.49-30.3,53.41-44.91,100.09-51.23"
    ",123.02-.58,2.1-1.15,4.32-1.73,6.71,2.32-5.49,4.94-11.19,7.9-17.04,13.39-26.42,36.61-72.21"
    ",83.93-88.86,13.54-4.76,25.96-6.06,33.79-6.37,1.47-.06,2.91-.08,4.3-.08,27.39,0,38.73,10.82"
    ",72,18.83,15.27,3.67,31.78,7.88,49.5,7.88,9.36,0,19.06-1.17,29.1-4.22,36.49-11.06,56.44"
    "-41.33,63.25-51.53,15.36-23.02,19.95-45.23,21.9-55.14,2.47-12.57,3.14-23.85,3.04-33.14"
    "-6.32-7.35-12.92-14.91-19.87-22.86,0,0-17.39-19.89-51.98-49.48C282.51,3.39,272.5,0,263.85"
    ',0"/>'
    "</svg>"
)


def _swagger_html(openapi_url: str) -> HTMLResponse:
    return HTMLResponse(f"""<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<title>Softmax API</title>
<link rel="icon" type="image/png" sizes="32x32"
      href="data:image/png;base64,{_FAVICON_B64}">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css">
<style>
  body {{ margin: 0; background: #fafbfc; }}
  .brand-bar {{
    background: #0e2758;
    padding: 12px 24px;
    display: flex;
    align-items: center;
    gap: 14px;
  }}
  .brand-bar .logo svg path {{
    stroke: #fff;
    stroke-width: 12;
  }}
  .brand-bar .title {{
    color: #fff;
    font-family: system-ui, -apple-system, sans-serif;
    font-size: 18px;
    font-weight: 600;
    letter-spacing: 0.02em;
  }}
  /* Swagger overrides */
  .swagger-ui .topbar {{ display: none; }}
  .swagger-ui .info hgroup.main h2.title {{ color: #0e2758; }}
  .swagger-ui .opblock.opblock-get .opblock-summary-method {{ background: #859ebe; }}
  .swagger-ui .btn.execute {{ background: #0e2758; border-color: #0e2758; }}
  .swagger-ui .btn.execute:hover {{ background: #bbccf3; color: #0e2758; border-color: #bbccf3; }}
</style>
</head><body>
<div class="brand-bar">
  <div class="logo">{_LOGO_SVG}</div>
  <span class="title">Softmax</span>
</div>
<div id="swagger-ui"></div>
<script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
<script>SwaggerUIBundle({{url: "{openapi_url}", dom_id: "#swagger-ui"}})</script>
</body></html>""")
