from fastapi import APIRouter, Depends, HTTPException, Request, Form
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import select
from datetime import datetime
from app.database import get_db
from app import models, schemas
from app.services.watcher_service import scheduler
from app.routes.auth import get_current_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def format_datetime(value):
    """Format datetime to exclude microseconds"""
    if value is None:
        return '-'
    if isinstance(value, datetime):
        return value.strftime('%Y-%m-%d %H:%M:%S')
    return str(value)


templates.env.filters['format_datetime'] = format_datetime


def _ensure_user(request: Request):
    if not get_current_user(request):
        raise HTTPException(status_code=401, detail="Unauthorized")


# UI ROUTES
@router.get("/")
def dashboard(request: Request, db: Session = Depends(get_db)):
    if not get_current_user(request):
        return RedirectResponse(url="/login", status_code=303)
    watchers = db.execute(select(models.Watcher)).scalars().all()
    return templates.TemplateResponse("dashboard.html", {"request": request, "watchers": watchers})


@router.get("/watchers/new")
def new_watcher_page(request: Request):
    if not get_current_user(request):
        return RedirectResponse(url="/login", status_code=303)
    return templates.TemplateResponse("watcher_form.html", {"request": request, "watcher": None})


@router.post("/watchers/new")
def create_watcher(
    request: Request,
    url: str = Form(...),
    phrase: str = Form(...),
    interval_minutes: int = Form(...),
    emails: str = Form(""),
    enabled: bool = Form(False),
    db: Session = Depends(get_db),
):
    if not get_current_user(request):
        return RedirectResponse(url="/login", status_code=303)
    watcher = models.Watcher(
        url=url.strip(),
        phrase=phrase.strip(),
        interval_minutes=max(1, interval_minutes),
        emails=emails,
        enabled=enabled,
    )
    db.add(watcher)
    db.commit()
    db.refresh(watcher)
    scheduler.reschedule(watcher)
    return RedirectResponse(url="/", status_code=303)


@router.get("/watchers/{watcher_id}/edit")
def edit_watcher_page(watcher_id: int, request: Request, db: Session = Depends(get_db)):
    if not get_current_user(request):
        return RedirectResponse(url="/login", status_code=303)
    watcher = db.get(models.Watcher, watcher_id)
    if not watcher:
        raise HTTPException(status_code=404, detail="Watcher not found")
    return templates.TemplateResponse("watcher_form.html", {"request": request, "watcher": watcher})


@router.post("/watchers/{watcher_id}/edit")
def update_watcher(
    watcher_id: int,
    request: Request,
    url: str = Form(...),
    phrase: str = Form(...),
    interval_minutes: int = Form(...),
    emails: str = Form(""),
    enabled: bool = Form(False),
    db: Session = Depends(get_db),
):
    if not get_current_user(request):
        return RedirectResponse(url="/login", status_code=303)
    watcher = db.get(models.Watcher, watcher_id)
    if not watcher:
        raise HTTPException(status_code=404, detail="Watcher not found")
    watcher.url = url.strip()
    watcher.phrase = phrase.strip()
    watcher.interval_minutes = max(1, interval_minutes)
    watcher.emails = emails
    watcher.enabled = enabled
    db.commit()
    db.refresh(watcher)
    scheduler.reschedule(watcher)
    return RedirectResponse(url="/", status_code=303)


@router.post("/watchers/{watcher_id}/toggle")
def toggle_watcher(watcher_id: int, request: Request, db: Session = Depends(get_db)):
    if not get_current_user(request):
        return RedirectResponse(url="/login", status_code=303)
    watcher = db.get(models.Watcher, watcher_id)
    if not watcher:
        raise HTTPException(status_code=404, detail="Watcher not found")
    watcher.enabled = not watcher.enabled
    db.commit()
    db.refresh(watcher)
    scheduler.reschedule(watcher)
    return RedirectResponse(url="/", status_code=303)


@router.post("/watchers/{watcher_id}/delete")
def delete_watcher(watcher_id: int, request: Request, db: Session = Depends(get_db)):
    if not get_current_user(request):
        return RedirectResponse(url="/login", status_code=303)
    watcher = db.get(models.Watcher, watcher_id)
    if watcher:
        db.delete(watcher)
        db.commit()
        scheduler.remove_job(watcher_id)
    return RedirectResponse(url="/", status_code=303)


@router.post("/watchers/{watcher_id}/run")
def run_now(watcher_id: int, request: Request):
    if not get_current_user(request):
        return RedirectResponse(url="/login", status_code=303)
    queued = scheduler.manual_check(watcher_id)
    if queued:
        return RedirectResponse(url=f"/watchers/{watcher_id}/logs-view?queued=1", status_code=303)
    else:
        return RedirectResponse(url=f"/watchers/{watcher_id}/logs-view?busy=1", status_code=303)


@router.get("/watchers/{watcher_id}/logs-view")
def view_logs(watcher_id: int, request: Request, db: Session = Depends(get_db)):
    if not get_current_user(request):
        return RedirectResponse(url="/login", status_code=303)
    watcher = db.get(models.Watcher, watcher_id)
    if not watcher:
        raise HTTPException(status_code=404, detail="Watcher not found")
    logs = (
        db.execute(
            select(models.CheckLog)
            .where(models.CheckLog.watcher_id == watcher_id)
            .order_by(models.CheckLog.checked_at.desc())
            .limit(50)
        )
        .scalars()
        .all()
    )
    return templates.TemplateResponse(
        "logs.html", {"request": request, "watcher": watcher, "logs": logs}
    )


# API ROUTES
@router.get("/watchers", response_model=list[schemas.WatcherOut])
def list_watchers(request: Request, db: Session = Depends(get_db)):
    _ensure_user(request)
    watchers = db.execute(select(models.Watcher)).scalars().all()
    return watchers


@router.post("/watchers", response_model=schemas.WatcherOut)
def api_create_watcher(request: Request, data: schemas.WatcherCreate, db: Session = Depends(get_db)):
    _ensure_user(request)
    watcher = models.Watcher(**data.model_dump())
    db.add(watcher)
    db.commit()
    db.refresh(watcher)
    scheduler.reschedule(watcher)
    return watcher


@router.get("/watchers/{watcher_id}", response_model=schemas.WatcherOut)
def api_get_watcher(watcher_id: int, request: Request, db: Session = Depends(get_db)):
    _ensure_user(request)
    watcher = db.get(models.Watcher, watcher_id)
    if not watcher:
        raise HTTPException(status_code=404, detail="Watcher not found")
    return watcher


@router.put("/watchers/{watcher_id}", response_model=schemas.WatcherOut)
def api_update_watcher(watcher_id: int, request: Request, updated: schemas.WatcherUpdate, db: Session = Depends(get_db)):
    _ensure_user(request)
    watcher = db.get(models.Watcher, watcher_id)
    if not watcher:
        raise HTTPException(status_code=404, detail="Watcher not found")
    for field in ["url", "phrase", "interval_minutes", "emails", "enabled"]:
        setattr(watcher, field, getattr(updated, field))
    db.commit()
    db.refresh(watcher)
    scheduler.reschedule(watcher)
    return watcher


@router.delete("/watchers/{watcher_id}")
def api_delete_watcher(watcher_id: int, request: Request, db: Session = Depends(get_db)):
    _ensure_user(request)
    watcher = db.get(models.Watcher, watcher_id)
    if not watcher:
        raise HTTPException(status_code=404, detail="Watcher not found")
    db.delete(watcher)
    db.commit()
    scheduler.remove_job(watcher_id)
    return JSONResponse({"deleted": watcher_id})


@router.post("/watchers/{watcher_id}/run-check")
def api_run_check(watcher_id: int, request: Request):
    _ensure_user(request)
    queued = scheduler.manual_check(watcher_id)
    return {"status": "queued" if queued else "already_running"}


@router.get("/watchers/{watcher_id}/logs", response_model=list[schemas.LogOut])
def api_logs(watcher_id: int, request: Request, limit: int = 50, db: Session = Depends(get_db)):
    _ensure_user(request)
    logs = (
        db.execute(
            select(models.CheckLog)
            .where(models.CheckLog.watcher_id == watcher_id)
            .order_by(models.CheckLog.checked_at.desc())
            .limit(limit)
        )
        .scalars()
        .all()
    )
    return logs
