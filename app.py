from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from config import Settings, get_settings
from agent.flow import AgentFlow


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
async def run_quiz(req: RunRequest) -> RunResponse:
    if req.secret != settings.student_secret:
        # The brief expects HTTP 403 for invalid secrets.
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid secret")

    agent = AgentFlow(
        initial_url=req.url,
        email=req.email,
        settings=settings,
    )

    result = await agent.run()

    return RunResponse(status="ok", detail=result)

