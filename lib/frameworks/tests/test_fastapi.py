from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_application():
    app = FastAPI()

    @app.get("/")
    def hello():
        return {"message": "hello"}

    assert TestClient(app).get("/").json() == {"message": "hello"}
