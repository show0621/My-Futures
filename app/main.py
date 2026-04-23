from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.strategy import SignalService

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="台指波段監控與虛擬交易")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
service = SignalService(symbol="^TWII")


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/api/signal")
def get_signal() -> dict:
    try:
        return service.get_latest()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Signal service error: {exc}") from exc


@app.post("/api/refresh")
def force_refresh() -> dict:
    try:
        return service.refresh()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Refresh failed: {exc}") from exc
