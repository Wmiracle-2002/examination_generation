import sys
import io
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from app.database import init_db
from app.routers import exam

app = FastAPI(title="智能组卷系统")

app.include_router(exam.router, prefix="/api")

for d in ["uploads", "outputs", "static/images"]:
    Path(d).mkdir(parents=True, exist_ok=True)

app.mount("/static", StaticFiles(directory="static"), name="static")

init_db()


@app.get("/", response_class=HTMLResponse)
def index():
    return Path("app/templates/index.html").read_text(encoding="utf-8")

