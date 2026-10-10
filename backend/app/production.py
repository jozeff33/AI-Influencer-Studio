"""V0.3 generation jobs. Additive tables; no mutation of V0.1/V0.2 schema.

Provider calls are explicit opt-in and never run during prompt preparation.
The prototype is local-only and does not implement production IAM/workers.
"""
import base64
import binascii
from datetime import datetime, timezone
import os
import uuid
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from .main import (Base, IdentityVersion, MediaAsset, MEDIA_DIR, IMAGE_MODEL,
                   app, checked_character, db, engine,
                   make_prompt, save_asset, tenant)

router = APIRouter()


class GenerationJob(Base):
    __tablename__ = "generation_jobs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(80), index=True)
    character_id: Mapped[str] = mapped_column(String(36), ForeignKey("characters.id"), index=True)
    identity_id: Mapped[str] = mapped_column(String(36), ForeignKey("identity_versions.id"))
    reference_asset_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    media_type: Mapped[str] = mapped_column(String(12))
    provider: Mapped[str] = mapped_column(String(30))
    model: Mapped[str] = mapped_column(String(80))
    scene: Mapped[str] = mapped_column(Text)
    prompt_snapshot: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="prepared")
    provider_job_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    output_asset_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    output_file_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    duration: Mapped[int] = mapped_column(Integer, default=5)
    ratio: Mapped[str] = mapped_column(String(20), default="1280:720")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class ConsistencyReview(Base):
    __tablename__ = "consistency_reviews"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(80), index=True)
    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("generation_jobs.id"), index=True)
    face: Mapped[int] = mapped_column(Integer)
    hair: Mapped[int] = mapped_column(Integer)
    wardrobe: Mapped[int] = mapped_column(Integer)
    style: Mapped[int] = mapped_column(Integer)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


# Additive create: V0.1/V0.2 tables and rows, including 'قمر', stay unchanged.
# Use proper versioned migrations before a production release.
Base.metadata.create_all(engine, checkfirst=True)


class JobIn(BaseModel):
    media_type: str = Field(pattern="^(image|video)$")
    scene: str = Field(min_length=5, max_length=2500)
    identity_id: str | None = None
    reference_asset_id: str | None = None
    duration: int = Field(default=5, ge=2, le=10)
    ratio: str = Field(default="1280:720", pattern="^(1280:720|720:1280)$")


class ReviewIn(BaseModel):
    face: bool
    hair: bool
    wardrobe: bool
    style: bool
    notes: str = Field(default="", max_length=1000)


def paid_enabled() -> bool:
    return os.getenv("ENABLE_PAID_GENERATION", "false").lower() == "true"


def get_provider_config():
    return {
        "image": {"provider": "openai", "model": IMAGE_MODEL,
                  "configured": bool(os.getenv("OPENAI_API_KEY", "").strip()), "live_enabled": paid_enabled()},
        "video": {"provider": "runway", "model": os.getenv("RUNWAY_VIDEO_MODEL", "gen4.5"),
                  "configured": bool(os.getenv("RUNWAYML_API_SECRET", "").strip()), "live_enabled": paid_enabled()},
        "notes": "Video via Runway; Sora Videos API retired 2026-09-24. Paid calls require explicit submit and ENABLE_PAID_GENERATION=true."
    }


def find_identity(session: Session, org: str, cid: str, requested: str | None):
    query = select(IdentityVersion).where(IdentityVersion.organization_id == org, IdentityVersion.character_id == cid)
    if requested:
        item = session.scalar(query.where(IdentityVersion.id == requested))
    else:
        item = session.scalar(query.order_by(IdentityVersion.version.desc()).limit(1))
    if item is None:
        raise HTTPException(409, "Create or select a valid identity version first")
    return item


def checked_job(session: Session, org: str, job_id: str) -> GenerationJob:
    job = session.scalar(select(GenerationJob).where(GenerationJob.id == job_id, GenerationJob.organization_id == org))
    if job is None:
        raise HTTPException(404, "Generation job not found")
    return job


def job_out(j: GenerationJob):
    return {
        "id": j.id, "character_id": j.character_id, "identity_id": j.identity_id,
        "reference_asset_id": j.reference_asset_id, "media_type": j.media_type,
        "provider": j.provider, "model": j.model, "scene": j.scene,
        "prompt": j.prompt_snapshot, "status": j.status,
        "progress": j.progress, "duration": j.duration, "ratio": j.ratio,
        "output_asset_id": j.output_asset_id,
        "video_url": "/jobs/" + j.id + "/video" if j.output_file_name else None,
        "error_code": j.error_code, "created_at": j.created_at.isoformat(),
    }


@router.get("/providers")
def providers(org: str = Depends(tenant)):
    return get_provider_config()


@router.post("/characters/{character_id}/jobs", status_code=201)
def prepare_job(character_id: str, data: JobIn, org: str = Depends(tenant), session: Session = Depends(db)):
    c = checked_character(session, org, character_id)
    ident = find_identity(session, org, character_id, data.identity_id)
    if data.reference_asset_id:
        asset = session.scalar(select(MediaAsset).where(
            MediaAsset.id == data.reference_asset_id, MediaAsset.organization_id == org,
            MediaAsset.character_id == character_id, MediaAsset.identity_id == ident.id))
        if asset is None or asset.mime_type not in ("image/png", "image/jpeg", "image/webp"):
            raise HTTPException(404, "Reference image for this identity not found")
    if data.media_type == "video" and data.duration not in (5, 10):
        raise HTTPException(422, "Runway duration must be 5 or 10 seconds")
    kind = data.media_type
    provider = "openai" if kind == "image" else "runway"
    model = IMAGE_MODEL if kind == "image" else os.getenv("RUNWAY_VIDEO_MODEL", "gen4.5")
    prompt = make_prompt(c, ident, data.scene)
    if kind == "video":
        prompt += " Natural continuous motion and stable recognizable appearance; no sudden identity changes."
    job = GenerationJob(id=str(uuid.uuid4()), organization_id=org, character_id=character_id,
                        identity_id=ident.id, reference_asset_id=data.reference_asset_id,
                        media_type=kind, provider=provider, model=model, scene=data.scene,
                        prompt_snapshot=prompt, duration=data.duration, ratio=data.ratio)
    session.add(job)
    session.commit()
    session.refresh(job)
    return job_out(job)


@router.get("/characters/{character_id}/jobs")
def list_jobs(character_id: str, org: str = Depends(tenant), session: Session = Depends(db)):
    checked_character(session, org, character_id)
    jobs = session.scalars(select(GenerationJob).where(GenerationJob.organization_id == org,
                                                       GenerationJob.character_id == character_id)
                           .order_by(GenerationJob.created_at.desc()).limit(100)).all()
    return [job_out(j) for j in jobs]


@router.get("/jobs/{job_id}")
def get_job(job_id: str, org: str = Depends(tenant), session: Session = Depends(db)):
    return job_out(checked_job(session, org, job_id))


def provider_headers(kind: str):
    if kind == "image":
        key = os.getenv("OPENAI_API_KEY", "").strip()
        return {"Authorization": "Bearer " + key}
    key = os.getenv("RUNWAYML_API_SECRET", "").strip()
    return {"Authorization": "Bearer " + key, "X-Runway-Version": "2024-11-06"}


def reference_image(session: Session, job: GenerationJob):
    if not job.reference_asset_id:
        return None
    asset = session.scalar(select(MediaAsset).where(
        MediaAsset.id == job.reference_asset_id, MediaAsset.organization_id == job.organization_id,
        MediaAsset.character_id == job.character_id, MediaAsset.identity_id == job.identity_id))
    if not asset:
        raise HTTPException(404, "Reference image no longer exists")
    file = MEDIA_DIR / asset.file_name
    if not file.exists():
        raise HTTPException(404, "Reference media file missing")
    data = file.read_bytes()
    if not data or len(data) > 8 * 1024 * 1024:
        raise HTTPException(422, "Reference file not usable")
    return asset, data


def image_generate(session: Session, job: GenerationJob):
    ref = reference_image(session, job)
    headers = provider_headers("image")
    try:
        if ref:
            asset, raw = ref
            response = httpx.post("https://api.openai.com/v1/images/edits", headers=headers,
                                  data={"model": job.model, "prompt": job.prompt_snapshot, "size": "1024x1024"},
                                  files={"image": (asset.file_name, raw, asset.mime_type)}, timeout=180.0)
        else:
            response = httpx.post("https://api.openai.com/v1/images/generations", headers=headers,
                                  json={"model": job.model, "prompt": job.prompt_snapshot,
                                        "size": "1024x1024", "n": 1}, timeout=180.0)
        response.raise_for_status()
        image_data = base64.b64decode(response.json()["data"][0]["b64_json"], validate=True)
        c = checked_character(session, job.organization_id, job.character_id)
        identity = find_identity(session, job.organization_id, job.character_id, job.identity_id)
        saved = save_asset(image_data, "generated", c, identity, job.scene, session)
        job.output_asset_id = saved["id"]
        job.progress = 100
        job.status = "completed"
    except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError, binascii.Error, HTTPException) as exc:
        job.status = "failed"
        job.error_code = "IMAGE_PROVIDER_FAILED"
        # Do not expose upstream bodies or secrets in responses.
        session.commit()
        raise HTTPException(502, "Image generation failed; job saved with generic error") from exc


def video_submit(session: Session, job: GenerationJob):
    ref = reference_image(session, job)
    data = {"model": job.model, "promptText": job.prompt_snapshot,
            "ratio": job.ratio, "duration": job.duration}
    if ref:
        asset, raw = ref
        data["promptImage"] = "data:" + asset.mime_type + ";base64," + base64.b64encode(raw).decode("ascii")
    try:
        response = httpx.post("https://api.dev.runwayml.com/v1/image_to_video",
                              headers={**provider_headers("video"), "Content-Type": "application/json"},
                              json=data, timeout=45.0)
        response.raise_for_status()
        job.provider_job_id = str(response.json()["id"])
        job.status = "queued"
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        job.status = "failed"
        job.error_code = "VIDEO_PROVIDER_FAILED"
        session.commit()
        raise HTTPException(502, "Video submission failed; job saved with generic error") from exc


@router.post("/jobs/{job_id}/submit")
def submit_job(job_id: str, org: str = Depends(tenant), session: Session = Depends(db)):
    job = checked_job(session, org, job_id)
    if job.status != "prepared":
        raise HTTPException(409, "This job has already been submitted or processed")
    if not paid_enabled():
        raise HTTPException(503, "Paid generation disabled; set ENABLE_PAID_GENERATION=true explicitly")
    if not os.getenv("OPENAI_API_KEY" if job.media_type == "image" else "RUNWAYML_API_SECRET", "").strip():
        raise HTTPException(503, "Selected provider is not configured")
    # Commit state before request. A crashed request is not automatically retried (cost safety).
    job.status = "submitting"
    session.commit()
    if job.media_type == "image":
        image_generate(session, job)
    else:
        video_submit(session, job)
    session.commit()
    session.refresh(job)
    return job_out(job)


def trusted_runway_output(url: str) -> bool:
    try:
        parsed = urlsplit(url)
        hostname = parsed.hostname or ""
        if parsed.scheme != "https" or parsed.username or parsed.password or parsed.port not in (None, 443):
            return False
        # Exact host or subdomain only. Never accept arbitrary provider output URL.
        return any(hostname == d or hostname.endswith("." + d) for d in ("cloudfront.net", "runwayml.com"))
    except ValueError:
        return False


def archive_video(url: str, job: GenerationJob):
    if not trusted_runway_output(url):
        raise ValueError("Untrusted output host")
    max_bytes = 120 * 1024 * 1024
    video_name = job.id + ".mp4"
    target = MEDIA_DIR / video_name
    try:
        with httpx.stream("GET", url, timeout=90.0, follow_redirects=False) as response:
            response.raise_for_status()
            if 300 <= response.status_code < 400:
                raise ValueError("Redirect not allowed")
            total = 0
            first = b""
            with target.open("wb") as out:
                for chunk in response.iter_bytes(1024 * 1024):
                    total += len(chunk)
                    if total > max_bytes:
                        raise ValueError("Video too large")
                    if len(first) < 12:
                        first = (first + chunk)[:12]
                    out.write(chunk)
            if total < 12 or first[4:8] != b"ftyp":
                raise ValueError("Not an MP4")
        job.output_file_name = video_name
    except Exception:
        target.unlink(missing_ok=True)
        raise


@router.post("/jobs/{job_id}/refresh")
def refresh_job(job_id: str, org: str = Depends(tenant), session: Session = Depends(db)):
    job = checked_job(session, org, job_id)
    if job.media_type != "video":
        raise HTTPException(409, "Only video tasks need polling")
    if job.status not in ("queued", "processing", "completed_unarchived"):
        return job_out(job)
    if not job.provider_job_id or not os.getenv("RUNWAYML_API_SECRET", "").strip():
        raise HTTPException(503, "Video provider is not configured")
    try:
        response = httpx.get("https://api.dev.runwayml.com/v1/tasks/" + job.provider_job_id,
                             headers=provider_headers("video"), timeout=30.0)
        response.raise_for_status()
        result = response.json()
        status = result.get("status", "")
        if status == "SUCCEEDED":
            outputs = result.get("output", [])
            try:
                if not outputs or not isinstance(outputs[0], str):
                    raise ValueError("Missing output")
                archive_video(outputs[0], job)
                job.status, job.progress = "completed", 100
                job.error_code = None
            except (httpx.HTTPError, ValueError, OSError):
                job.status = "completed_unarchived"
                job.error_code = "VIDEO_ARCHIVE_FAILED"
        elif status in ("FAILED", "CANCELED"):
            job.status = "failed"
            job.error_code = "VIDEO_PROVIDER_FAILED"
        else:
            job.status = "processing" if status == "RUNNING" else "queued"
            job.progress = 0
        session.commit()
        session.refresh(job)
        return job_out(job)
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        raise HTTPException(502, "Could not refresh video job; try again later") from exc


@router.get("/jobs/{job_id}/video")
def read_video(job_id: str, org: str = Depends(tenant), session: Session = Depends(db)):
    job = checked_job(session, org, job_id)
    if not job.output_file_name or job.status != "completed":
        raise HTTPException(404, "Video is not archived")
    path = MEDIA_DIR / (job.id + ".mp4")
    if not path.is_file():
        raise HTTPException(404, "Video file missing")
    return FileResponse(path, media_type="video/mp4", headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})


@router.post("/jobs/{job_id}/review", status_code=201)
def review_job(job_id: str, payload: ReviewIn, org: str = Depends(tenant), session: Session = Depends(db)):
    job = checked_job(session, org, job_id)
    if job.status != "completed":
        raise HTTPException(409, "Complete and archive the media before human review")
    values = payload.model_dump()
    review = ConsistencyReview(id=str(uuid.uuid4()), organization_id=org, job_id=job_id,
                               **{field: int(values[field]) for field in ("face", "hair", "wardrobe", "style")},
                               notes=values["notes"])
    session.add(review)
    session.commit()
    return {"id": review.id, "job_id": job_id, "score": sum(getattr(review, x) for x in ("face", "hair", "wardrobe", "style")) * 25,
            "method": "human_checklist", "notes": review.notes}


@router.get("/jobs/{job_id}/reviews")
def get_reviews(job_id: str, org: str = Depends(tenant), session: Session = Depends(db)):
    checked_job(session, org, job_id)
    reviews = session.scalars(select(ConsistencyReview).where(ConsistencyReview.job_id == job_id,
                         ConsistencyReview.organization_id == org).order_by(ConsistencyReview.created_at.desc())).all()
    return [{"id": r.id, "score": 25 * (r.face + r.hair + r.wardrobe + r.style), "notes": r.notes,
             "method": "human_checklist", "created_at": r.created_at.isoformat()} for r in reviews]


app.include_router(router)
