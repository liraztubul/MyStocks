from collections.abc import Iterator
from contextlib import contextmanager
from decimal import localcontext

# Python's default Decimal context keeps 28 significant digits, so even a product of two
# Numeric(28, 10) values can be silently rounded. 60 keeps those products and sums exact.
ENGINE_PRECISION = 60


@contextmanager
def exact() -> Iterator[None]:
    """Decimal context for P/L arithmetic. Results keep their digits after the block exits."""
    with localcontext() as ctx:
        ctx.prec = ENGINE_PRECISION
        yield
