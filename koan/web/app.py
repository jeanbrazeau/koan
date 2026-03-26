# Starlette app factory and route stubs.
# All endpoints return 501 until implemented in later tickets.

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route

if TYPE_CHECKING:
    from ..state import AppState

NOT_IMPL = Response("Not Implemented", status_code=501)


# -- Route handlers (stubs) --------------------------------------------------

async def landing_page(r: Request) -> Response:
    return NOT_IMPL


async def sse_stream(r: Request) -> Response:
    return NOT_IMPL


async def mcp_endpoint(r: Request) -> Response:
    return NOT_IMPL


async def api_start_run(r: Request) -> Response:
    return NOT_IMPL


async def api_answer(r: Request) -> Response:
    return NOT_IMPL


async def api_artifact_review(r: Request) -> Response:
    return NOT_IMPL


async def api_workflow_decision(r: Request) -> Response:
    return NOT_IMPL


async def api_artifacts(r: Request) -> Response:
    return NOT_IMPL


async def static_files(r: Request) -> Response:
    return NOT_IMPL


# -- App factory --------------------------------------------------------------

def create_app(app_state: AppState) -> Starlette:
    async def startup_handler() -> None:
        from ..driver import driver_main
        asyncio.create_task(driver_main(app_state))

    routes = [
        Route("/", landing_page),
        Route("/events", sse_stream),
        Route("/mcp", mcp_endpoint, methods=["POST"]),
        Route("/api/start-run", api_start_run, methods=["POST"]),
        Route("/api/answer", api_answer, methods=["POST"]),
        Route("/api/artifact-review", api_artifact_review, methods=["POST"]),
        Route("/api/workflow-decision", api_workflow_decision, methods=["POST"]),
        Route("/api/artifacts/{path:path}", api_artifacts),
        Route("/static/{path:path}", static_files),
    ]

    return Starlette(routes=routes, on_startup=[startup_handler])
