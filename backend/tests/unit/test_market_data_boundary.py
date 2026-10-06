"""Default-deny by construction: no endpoint may reach the ungated market data service.

Two independent checks, so renaming or re-exporting can't slip past both:
- source: no module in app/api imports app.market_data.service (or names its getter);
- runtime: in FastAPI's resolved dependency graph, shared_market_data only ever appears as a
  dependency of user_market_data, the function that applies the stock-data allowlist.
"""

import ast
from collections.abc import Iterator, Sequence
from pathlib import Path

from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute
from starlette.routing import BaseRoute

from app.main import app
from app.market_data.access import user_market_data
from app.market_data.service import shared_market_data

API_DIR = Path(__file__).resolve().parents[2] / "app" / "api"
RAW_MODULE = "app.market_data.service"
RAW_NAMES = {"shared_market_data", "MarketData"}


def _violations(path: Path) -> Iterator[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == RAW_MODULE:
            yield f"{path.name}:{node.lineno} imports from {RAW_MODULE}"
        elif isinstance(node, ast.Import) and any(a.name == RAW_MODULE for a in node.names):
            yield f"{path.name}:{node.lineno} imports {RAW_MODULE}"
        elif isinstance(node, ast.Name | ast.Attribute):
            name = node.id if isinstance(node, ast.Name) else node.attr
            if name in RAW_NAMES:
                yield f"{path.name}:{node.lineno} uses {name}"


def test_no_router_module_touches_the_raw_service() -> None:
    files = sorted(API_DIR.glob("*.py"))
    assert files, "found no router modules; did app/api move?"
    violations = [v for f in files for v in _violations(f)]
    assert violations == [], "use app.market_data.access.UserMarketDataDep instead"


def _api_routes(routes: Sequence[BaseRoute]) -> Iterator[APIRoute]:
    # FastAPI 0.141 keeps an included router as a nested object (with original_router) instead
    # of flattening its routes into app.routes; older versions flatten. Handle both.
    for route in routes:
        if isinstance(route, APIRoute):
            yield route
        elif (inner := getattr(route, "original_router", None)) is not None:
            yield from _api_routes(inner.routes)


def _raw_dependency_parents(dependant: Dependant, parent: object) -> Iterator[object]:
    for sub in dependant.dependencies:
        if sub.call is shared_market_data:
            yield parent
        yield from _raw_dependency_parents(sub, sub.call)


def test_raw_service_is_only_reachable_through_the_gate() -> None:
    routes = list(_api_routes(app.routes))
    parents = [(r.path, p) for r in routes for p in _raw_dependency_parents(r.dependant, r.path)]
    assert parents, "no route uses market data at all; the check would pass vacuously"
    assert all(p is user_market_data for _, p in parents), parents
