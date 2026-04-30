"""deTilda web application — FastAPI entry point."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from core.version import APP_VERSION

app = FastAPI(title="deTilda", version=APP_VERSION)


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    return f"""
    <!DOCTYPE html>
    <html>
    <head><title>deTilda</title></head>
    <body>
        <h1>deTilda {APP_VERSION}</h1>
        <p>Сервис запущен и работает.</p>
    </body>
    </html>
    """


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "version": APP_VERSION}
