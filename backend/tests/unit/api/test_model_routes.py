from fastapi.testclient import TestClient
from fastapi import FastAPI

def test_model_list_endpoint():
    from api.v2.model_routes import router
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    
    response = client.get("/api/v2/models/list")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
