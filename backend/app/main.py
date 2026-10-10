import os
import uuid
from datetime import datetime, timezone
from typing import Optional
from fastapi import FastAPI, Depends, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, String, ForeignKey, DateTime, Text, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker, Session

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
Base.metadata.create_all(engine)  # Prototype only; use Alembic migrations for production.
app = FastAPI(title="AI Influencer Studio", version="0.1.0")
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
def health(): return {"status":"ok","version":"0.1.0"}
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
