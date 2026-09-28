import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

from contextlib import asynccontextmanager
from backend.database import init_db

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Always initialize schema
    init_db()
    # Seed master reference data (departments)
    try:
        from backend.scripts.seed_departments import seed_departments
        seed_departments()
    except Exception as e:
        print(f"Department seed notice: {e}")

    # Auto-seed initial demo dataset if database is fresh (e.g. on Render)
    try:
        from backend.database import SessionLocal
        from backend.models.section import RailwaySection
        db = SessionLocal()
        try:
            section_count = db.query(RailwaySection).count()
            if section_count == 0:
                print("Fresh deployment detected — generating initial demo dataset...")
                from backend.scripts.generate_synthetic_data import generate_synthetic_data
                generate_synthetic_data(seed=26027, recreate_tables=False)
        finally:
            db.close()
    except Exception as e:
        print(f"Demo data initialization notice: {e}")

    yield

# Auto-migrate / ensure tables and columns on module load
init_db()

app = FastAPI(
    title="SANGAM API",
    description="AI-Powered Joint Block Planning for Indian Railways",
    version="0.1.0",
    lifespan=lifespan,
)

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


from backend.routers import corridor, tasks, sections, plans, kpis, resources, rules
from backend.routers.conflicts import router as conflicts_router

app.include_router(corridor.router)
app.include_router(tasks.router)
app.include_router(sections.router)
app.include_router(plans.router)
app.include_router(kpis.router)
app.include_router(conflicts_router)
app.include_router(resources.router)
app.include_router(rules.router)


@app.get("/health")
def health_check():
    return {"status": "ok", "service": "SANGAM"}


# Static SPA frontend serving (for unified Render / Docker container deployment)
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi import HTTPException

frontend_dist = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend", "dist"))
assets_dir = os.path.join(frontend_dist, "assets")

if os.path.isdir(assets_dir):
    app.mount("/assets", StaticFiles(directory=assets_dir), name="static-assets")

if os.path.isdir(frontend_dist):
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        if full_path.startswith("api") or full_path in ("health", "docs", "redoc", "openapi.json"):
            raise HTTPException(status_code=404, detail="Not Found")
        file_path = os.path.join(frontend_dist, full_path)
        if full_path and os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(frontend_dist, "index.html"))


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
