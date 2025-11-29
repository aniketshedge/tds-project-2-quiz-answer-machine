from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from config import Settings, get_settings
from agent.flow import AgentFlow
from logging_utils import log_event
import asyncio


class RunRequest(BaseModel):
    email: str
    secret: str
    url: str


class RunResponse(BaseModel):
    status: str
    detail: str | None = None


settings: Settings = get_settings()
app = FastAPI(title="TDS Project 2 Quiz Answer Machine")


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """
    Return HTTP 400 for invalid JSON / payloads, as required by the brief.
    """
    status_code = status.HTTP_400_BAD_REQUEST
    log_event(
        "HTTP_BAD_REQUEST",
        method=request.method,
        path=request.url.path,
        client_host=request.client.host if request.client else None,
        status_code=status_code,
        detail="Invalid JSON or request body",
        errors=exc.errors(),
    )
    return JSONResponse(
        status_code=status_code,
        content={"detail": "Invalid JSON or request body", "errors": exc.errors()},
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(
    request: Request,
    exc: HTTPException,
) -> JSONResponse:
    """
    Log all HTTPException responses (e.g. 403 invalid secret,
    404 not found, 405 method not allowed) so that bad or
    malformed client attempts are captured in the logs.
    """
    log_event(
        "HTTP_EXCEPTION",
        method=request.method,
        path=request.url.path,
        client_host=request.client.host if request.client else None,
        status_code=exc.status_code,
        detail=exc.detail,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


@app.post("/run", response_model=RunResponse)
async def run_quiz(request: Request, req: RunRequest) -> RunResponse:
    if req.secret != settings.student_secret:
        # The brief expects HTTP 403 for invalid secrets.
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid secret")

    client_host = request.client.host if request.client else None
    log_event(
        "RECEIVED_POST",
        email=req.email,
        url=req.url,
        client_host=client_host,
    )

    agent = AgentFlow(
        initial_url=req.url,
        email=req.email,
        settings=settings,
    )

    async def _run_in_background() -> None:
        """
        Execute the agent flow without blocking the HTTP response.
        All outcomes are recorded in the log file.
        """
        try:
            result = await agent.run()
            log_event(
                "RUN_COMPLETED",
                email=req.email,
                url=req.url,
                result=result,
            )
        except Exception as exc:  # pragma: no cover - defensive catch-all
            log_event(
                "RUN_ERROR",
                email=req.email,
                url=req.url,
                error=str(exc),
            )

    # Fire-and-forget background execution; caller gets 200 immediately.
    asyncio.create_task(_run_in_background())

    return RunResponse(status="ok", detail="Accepted")
