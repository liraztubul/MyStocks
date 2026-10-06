"""Default-deny by construction: no endpoint may reach the ungated market data service.

Two independent checks, so renaming or re-exporting can't slip past both:
- source: no module in app/api imports app.market_data.service or .price_history (or names
  their ungated getters);
- runtime: in FastAPI's resolved dependency graph, each ungated getter only ever appears as a
  dependency of its gate (shared_market_data under user_market_data, shared_price_history under
  user_price_history), the functions that apply the stock-data allowlist.
"""

import ast
from collections.abc import Iterator, Sequence
from pathlib import Path

from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute
from starlette.routing import BaseRoute

from app.main import app
from app.market_data.access import user_market_data, user_price_history
from app.market_data.price_history import shared_price_history
from app.market_data.service import shared_market_data

# Each ungated getter and the only function allowed to depend on it.
GATES = {shared_market_data: user_market_data, shared_price_history: user_price_history}

API_DIR = Path(__file__).resolve().parents[2] / "app" / "api"
RAW_MODULES = {"app.market_data.service", "app.market_data.price_history"}
RAW_NAMES = {"shared_market_data", "MarketData", "shared_price_history", "PriceHistoryService"}


def _violations(path: Path) -> Iterator[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module in RAW_MODULES:
            yield f"{path.name}:{node.lineno} imports from {node.module}"
        elif isinstance(node, ast.Import) and any(a.name in RAW_MODULES for a in node.names):
            yield f"{path.name}:{node.lineno} imports a raw market data module"
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


def _raw_dependency_parents(
    dependant: Dependant, parent: object
) -> Iterator[tuple[object, object]]:
    for sub in dependant.dependencies:
        if sub.call in GATES:
            yield sub.call, parent
        yield from _raw_dependency_parents(sub, sub.call)


def test_raw_services_are_only_reachable_through_their_gates() -> None:
    routes = list(_api_routes(app.routes))
    uses = [
        (r.path, raw, p) for r in routes for raw, p in _raw_dependency_parents(r.dependant, r.path)
    ]
    for raw in GATES:
        assert any(u[1] is raw for u in uses), f"no route uses {raw.__name__}; the check is vacuous"
    assert all(parent is GATES[raw] for _, raw, parent in uses), uses
