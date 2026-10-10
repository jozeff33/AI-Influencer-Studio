import os
import uuid
from datetime import datetime, timezone
from typing import Optional
from fastapi import FastAPI, Depends, HTTPException, Header, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, String, ForeignKey, DateTime, Text, select, Integer, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker, Session
from fastapi.responses import FileResponse
from pathlib import Path
from PIL import Image, UnidentifiedImageError
from io import BytesIO
import base64
import httpx
import binascii

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./studio.db")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)
class Base(DeclarativeBase): pass
class Character(Base):
    __tablename__ = "characters"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(80), index=True)
    name: Mapped[str] = mapped_column(String(120))
    persona: Mapped[str] = mapped_column(Text, default="")
    language: Mapped[str] = mapped_column(String(30), default="ar-IQ")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
class Project(Base):
    __tablename__ = "content_projects"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(80), index=True)
    character_id: Mapped[str] = mapped_column(String(36), ForeignKey("characters.id"))
    title: Mapped[str] = mapped_column(String(200))
    script: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(30), default="draft")

class IdentityVersion(Base):
    __tablename__ = "identity_versions"
    __table_args__ = (UniqueConstraint("character_id", "version", name="uq_character_version"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(80), index=True)
    character_id: Mapped[str] = mapped_column(String(36), ForeignKey("characters.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    appearance: Mapped[str] = mapped_column(Text)
    wardrobe: Mapped[str] = mapped_column(Text, default="")
    visual_style: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class MediaAsset(Base):
    __tablename__ = "media_assets"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(80), index=True)
    character_id: Mapped[str] = mapped_column(String(36), ForeignKey("characters.id"), index=True)
    identity_id: Mapped[str] = mapped_column(String(36), ForeignKey("identity_versions.id"))
    kind: Mapped[str] = mapped_column(String(24))
    mime_type: Mapped[str] = mapped_column(String(40))
    file_name: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

Base.metadata.create_all(engine)  # Prototype only; use Alembic migrations for production.
app = FastAPI(title="AI Influencer Studio", version="0.4.0")
app.add_middleware(CORSMiddleware, allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:3000").split(","), allow_methods=["GET","POST"], allow_headers=["*"])

def db():
    with SessionLocal() as session: yield session

def tenant(x_org_id: str = Header(..., alias="X-Organization-ID"), x_api_key: str = Header(..., alias="X-API-Key")):
    expected = os.getenv("STUDIO_DEV_API_KEY", "")
    if not expected or x_api_key != expected: raise HTTPException(401, "Invalid API key")
    if not x_org_id.strip(): raise HTTPException(400, "Missing organization")
    return x_org_id

class CharacterIn(BaseModel):
    name: str = Field(min_length=1,max_length=120)
    persona: str = Field(default="",max_length=10000)
    language: str = Field(default="ar-IQ",max_length=30)
class ProjectIn(BaseModel):
    character_id: str
    title: str = Field(min_length=1,max_length=200)
    script: str = Field(default="",max_length=30000)

def char_out(c): return {"id":c.id,"name":c.name,"persona":c.persona,"language":c.language,"created_at":c.created_at.isoformat()}
def project_out(q): return {"id":q.id,"character_id":q.character_id,"title":q.title,"script":q.script,"status":q.status}
@app.get("/health")
def health(): return {"status":"ok","version":"0.4.0"}
@app.get("/characters")
def list_characters(org: str=Depends(tenant), session: Session=Depends(db)):
    return [char_out(c) for c in session.scalars(select(Character).where(Character.organization_id==org).order_by(Character.created_at.desc())).all()]
@app.post("/characters",status_code=201)
def create_character(data: CharacterIn,org: str=Depends(tenant),session: Session=Depends(db)):
    c=Character(id=str(uuid.uuid4()),organization_id=org,**data.model_dump());session.add(c);session.commit();session.refresh(c);return char_out(c)
@app.get("/projects")
def list_projects(org: str=Depends(tenant),session: Session=Depends(db)):
    return [project_out(q) for q in session.scalars(select(Project).where(Project.organization_id==org)).all()]
@app.post("/projects",status_code=201)
def create_project(data: ProjectIn,org: str=Depends(tenant),session: Session=Depends(db)):
    c=session.scalar(select(Character).where(Character.id==data.character_id,Character.organization_id==org))
    if c is None: raise HTTPException(404,"Character not found")
    q=Project(id=str(uuid.uuid4()),organization_id=org,**data.model_dump());session.add(q);session.commit();return project_out(q)

# V0.2 identity versions and media — prototype using local media storage.
MEDIA_DIR = Path(os.getenv("MEDIA_DIR", "./media")).resolve()
MEDIA_DIR.mkdir(parents=True, exist_ok=True)
IMAGE_MODEL = os.getenv("IMAGE_MODEL", "gpt-image-1-mini")

class IdentityIn(BaseModel):
    appearance: str = Field(min_length=10, max_length=3000)
    wardrobe: str = Field(default="", max_length=2000)
    visual_style: str = Field(default="photorealistic editorial portrait", max_length=1000)

class SceneIn(BaseModel):
    scene: str = Field(min_length=5, max_length=2500)

def checked_character(session: Session, org: str, cid: str):
    c = session.scalar(select(Character).where(Character.id == cid, Character.organization_id == org))
    if c is None:
        raise HTTPException(404, "Character not found")
    return c

def latest_identity(session: Session, org: str, cid: str):
    item = session.scalar(select(IdentityVersion).where(IdentityVersion.character_id == cid, IdentityVersion.organization_id == org).order_by(IdentityVersion.version.desc()).limit(1))
    if item is None:
        raise HTTPException(409, "Create an identity version first")
    return item

def identity_out(i):
    return {"id": i.id, "character_id": i.character_id, "version": i.version, "appearance": i.appearance, "wardrobe": i.wardrobe, "visual_style": i.visual_style, "created_at": i.created_at.isoformat()}

def asset_out(a):
    return {"id": a.id, "character_id": a.character_id, "identity_id": a.identity_id, "kind": a.kind, "mime_type": a.mime_type, "description": a.description, "url": "/assets/" + a.id, "created_at": a.created_at.isoformat()}

def make_prompt(c: Character, ident: IdentityVersion, scene: str):
    return (f"Create an original clearly fictional AI character, named {c.name}. "
            f"Preserve this character identity across all images: {ident.appearance}. "
            f"Wardrobe conventions: {ident.wardrobe}. Visual style: {ident.visual_style}. "
            f"Scene: {scene}. Keep the same recognizable features, adult-appropriate, "
            "avoid impersonating any real person, no misleading logos or signatures.")

@app.get("/characters/{character_id}/identity")
def get_identity(character_id: str, org: str = Depends(tenant), session: Session = Depends(db)):
    checked_character(session, org, character_id)
    items = session.scalars(select(IdentityVersion).where(IdentityVersion.character_id == character_id, IdentityVersion.organization_id == org).order_by(IdentityVersion.version.desc())).all()
    return [identity_out(x) for x in items]

@app.post("/characters/{character_id}/identity", status_code=201)
def add_identity(character_id: str, data: IdentityIn, org: str = Depends(tenant), session: Session = Depends(db)):
    checked_character(session, org, character_id)
    v = session.scalar(select(func.max(IdentityVersion.version)).where(IdentityVersion.character_id == character_id)) or 0
    ident = IdentityVersion(id=str(uuid.uuid4()), character_id=character_id, organization_id=org, version=v+1, **data.model_dump())
    session.add(ident)
    session.commit()
    session.refresh(ident)
    return identity_out(ident)

@app.post("/characters/{character_id}/prompt-preview")
def prompt_preview(character_id: str, data: SceneIn, org: str = Depends(tenant), session: Session = Depends(db)):
    c = checked_character(session, org, character_id)
    ident = latest_identity(session, org, character_id)
    return {"identity_version": ident.version, "prompt": make_prompt(c, ident, data.scene), "generation_enabled": bool(os.getenv("OPENAI_API_KEY"))}

@app.get("/characters/{character_id}/assets")
def list_assets(character_id: str, org: str = Depends(tenant), session: Session = Depends(db)):
    checked_character(session, org, character_id)
    return [asset_out(a) for a in session.scalars(select(MediaAsset).where(MediaAsset.character_id == character_id, MediaAsset.organization_id == org).order_by(MediaAsset.created_at.desc())).all()]

# Validate actual file contents, not just the browser-provided MIME type.
def validate_image(content: bytes):
    if len(content) > 8 * 1024 * 1024 or not content:
        raise HTTPException(413, "Image must be 8MB or smaller")
    try:
        Image.MAX_IMAGE_PIXELS = 30_000_000
        img = Image.open(BytesIO(content))
        fmt = img.format
        img.verify()
        if fmt not in ("PNG", "JPEG", "WEBP"):
            raise ValueError("unsupported")
    except (UnidentifiedImageError, ValueError, OSError, Image.DecompressionBombError):
        raise HTTPException(415, "Upload a valid PNG, JPEG, or WEBP image")
    return {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}[fmt], {"PNG": ".png", "JPEG": ".jpg", "WEBP": ".webp"}[fmt]

def save_asset(content: bytes, kind: str, c: Character, ident: IdentityVersion, description: str, session: Session):
    mime, suffix = validate_image(content)
    asset_id = str(uuid.uuid4())
    name = asset_id + suffix
    (MEDIA_DIR / name).write_bytes(content)
    obj = MediaAsset(id=asset_id, organization_id=c.organization_id, character_id=c.id, identity_id=ident.id, kind=kind, mime_type=mime, file_name=name, description=description)
    session.add(obj)
    try:
        session.commit()
        session.refresh(obj)
    except Exception:
        (MEDIA_DIR / name).unlink(missing_ok=True)
        raise
    return asset_out(obj)

@app.post("/characters/{character_id}/references", status_code=201)
async def add_reference(character_id: str, file: UploadFile = File(...), org: str = Depends(tenant), session: Session = Depends(db)):
    c = checked_character(session, org, character_id)
    ident = latest_identity(session, org, character_id)
    content = await file.read(8 * 1024 * 1024 + 1)
    return save_asset(content, "reference", c, ident, "User-provided reference; only upload images you have rights to use", session)

@app.get("/assets/{asset_id}")
def read_asset(asset_id: str, org: str = Depends(tenant), session: Session = Depends(db)):
    obj = session.scalar(select(MediaAsset).where(MediaAsset.id == asset_id, MediaAsset.organization_id == org))
    if obj is None:
        raise HTTPException(404, "Asset not found")
    path = MEDIA_DIR / obj.file_name
    if not path.is_file():
        raise HTTPException(404, "Media file missing")
    return FileResponse(path, media_type=obj.mime_type, headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})

@app.post("/characters/{character_id}/images", status_code=201)
def generate_image(character_id: str, data: SceneIn, org: str = Depends(tenant), session: Session = Depends(db)):
    c = checked_character(session, org, character_id)
    ident = latest_identity(session, org, character_id)
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if os.getenv("ENABLE_PAID_GENERATION", "false").lower() != "true":
        raise HTTPException(503, "Paid generation is disabled; explicitly enable it before making requests")
    if not api_key:
        raise HTTPException(503, "Image provider not configured: add OPENAI_API_KEY to .env")
    prompt = make_prompt(c, ident, data.scene)
    try:
        response = httpx.post("https://api.openai.com/v1/images/generations",
            headers={"Authorization": "Bearer " + api_key},
            json={"model": IMAGE_MODEL, "prompt": prompt, "size": "1024x1024", "n": 1}, timeout=120.0)
        response.raise_for_status()
        payload = response.json()
        result = base64.b64decode(payload["data"][0]["b64_json"], validate=True)
    except (httpx.HTTPError, ValueError, KeyError, IndexError, binascii.Error) as exc:
        # Never echo provider responses or credentials into user-visible errors.
        raise HTTPException(502, "Image provider request failed; inspect server logs") from exc
    return save_asset(result, "generated", c, ident, data.scene, session)

# Imported last to keep existing V0.1/V0.2 endpoints and models stable.
from . import production  # noqa: F401

# V0.4 additive story engine and serialized reels.
from . import story  # noqa: F401
