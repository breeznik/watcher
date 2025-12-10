import logging
from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware
from starlette.staticfiles import StaticFiles
from app.core.config import get_settings
from app.db.database import Base, engine
from app.routes import auth, watchers
from app.services.watcher_service import scheduler

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

settings = get_settings()

app = FastAPI(title=settings.app_name)
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key)
app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(auth.router)
app.include_router(watchers.router)


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
    scheduler.start()
    scheduler.load_and_schedule()


@app.on_event("shutdown")
def on_shutdown():
    scheduler.shutdown()


@app.get("/health")
def health():
    return {"status": "ok"}