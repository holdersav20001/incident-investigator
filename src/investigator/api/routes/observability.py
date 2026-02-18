"""GET /metrics  — return metric snapshot."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

router = APIRouter()


def _get_metrics(request: Request):  # type: ignore[return]
    return getattr(request.app.state, "metrics", None)


# ---------------------------------------------------------------------------
# GET /metrics
# ---------------------------------------------------------------------------

@router.get("/metrics", status_code=200)
def get_metrics(request: Request) -> dict[str, Any]:
    metrics = _get_metrics(request)
    if metrics is None:
        return {"counters": {}, "histograms": {}}
    return metrics.snapshot()
