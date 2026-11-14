"""HTTP contract tests for the additive Mars API."""
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.app.api.mars import router

app=FastAPI()
app.include_router(router,prefix="/api/v1")
client=TestClient(app)
DESIGN={"launch":"lv-standard","power":"pw-nuclear","comm":"cm-advanced",
        "landing":"ld-advanced","instruments":["ins-camera","ins-spectro","ins-drill"]}

def test_mars_catalog_endpoint():
    response=client.get("/api/v1/mars/catalog")
    assert response.status_code==200
    assert set(response.json()["categories"])=={"launch","power","comm","instruments","landing"}

def test_mars_evaluate_endpoint():
    response=client.post("/api/v1/mars/evaluate",json=DESIGN)
    assert response.status_code==200
    assert response.json()["valid"] is True

def test_mars_simulation_endpoint():
    response=client.post("/api/v1/mars/simulate",json=DESIGN)
    assert response.status_code==200
    assert response.json()["outcome"]=="SUCCESS"
    assert len(response.json()["stages"])==4

def test_mars_simulation_rejects_incomplete_design():
    response=client.post("/api/v1/mars/simulate",json={"instruments":[]})
    assert response.status_code==422
