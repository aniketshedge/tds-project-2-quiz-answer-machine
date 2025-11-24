from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from config import Settings, get_settings
from agent.flow import AgentFlow
from logging_utils import log_event


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
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": "Invalid JSON or request body", "errors": exc.errors()},
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

    try:
        result = await agent.run()
        log_event(
            "RUN_COMPLETED",
            email=req.email,
            url=req.url,
            result=result,
        )
        return RunResponse(status="ok", detail=result)
    except Exception as exc:  # pragma: no cover - defensive catch-all
        log_event(
            "RUN_ERROR",
            email=req.email,
            url=req.url,
            error=str(exc),
        )
        # Per brief, secret matched so we must still return HTTP 200.
        return RunResponse(status="error", detail="Internal error while processing quiz.")

