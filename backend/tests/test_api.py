import os
os.environ["DATABASE_URL"] = "sqlite:///./test_studio.db"
os.environ["STUDIO_DEV_API_KEY"] = "test-secret"
from fastapi.testclient import TestClient
from app.main import app
client=TestClient(app)
def headers(org): return {"X-Organization-ID":org,"X-API-Key":"test-secret"}
def test_health(): assert client.get("/health").json()["status"]=="ok"
def test_requires_auth(): assert client.get("/characters").status_code==422
def test_tenant_isolation():
    r=client.post("/characters",headers=headers("org-a"),json={"name":"عشتار جديدة","persona":"شخصية افتراضية"})
    assert r.status_code==201
    cid=r.json()["id"]
    assert any(c["id"]==cid for c in client.get("/characters",headers=headers("org-a")).json())
    assert not any(c["id"]==cid for c in client.get("/characters",headers=headers("org-b")).json())
    assert client.post("/projects",headers=headers("org-b"),json={"character_id":cid,"title":"فيديو"}).status_code==404
    assert client.post("/projects",headers=headers("org-a"),json={"character_id":cid,"title":"فيديو"}).status_code==201
