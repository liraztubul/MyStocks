from fastapi import Request
from fastapi.responses import JSONResponse


class CodedHTTPError(Exception):
    """An HTTP error whose JSON body carries a machine-readable `code` next to `detail`, the same
    shape market-data errors use, so the frontend can react to the reason rather than the text."""

    def __init__(self, status_code: int, code: str, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.code = code
        self.detail = detail


async def coded_http_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, CodedHTTPError)
    return JSONResponse(
        status_code=exc.status_code, content={"detail": exc.detail, "code": exc.code}
    )
