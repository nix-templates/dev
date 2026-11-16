from flask import Flask


def test_application():
    app = Flask(__name__)

    @app.get("/")
    def hello():
        return "hello"

    assert app.test_client().get("/").data == b"hello"
