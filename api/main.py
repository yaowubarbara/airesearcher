"""FastAPI application for AI Researcher."""
import sys
from pathlib import Path
from contextlib import asynccontextmanager

# Ensure project root on path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.deps import get_db, get_vs
from api.routers import journals, discover, references, plan, write, review, submit, tasks, stats


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: initialize DB and vector store
    db = get_db()
    _ = get_vs()
    yield
    # Shutdown
    db.close()


app = FastAPI(
    title="AI Researcher API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3009"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount routers
app.include_router(journals.router, prefix="/api")
app.include_router(discover.router, prefix="/api")
app.include_router(references.router, prefix="/api")
app.include_router(plan.router, prefix="/api")
app.include_router(write.router, prefix="/api")
app.include_router(review.router, prefix="/api")
app.include_router(submit.router, prefix="/api")
app.include_router(tasks.router, prefix="/api")
app.include_router(stats.router, prefix="/api")


@app.get("/api/health")
async def health():
    return {"status": "ok"}
