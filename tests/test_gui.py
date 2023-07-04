from gui import app


def test_search_page():
    response = app.test_client().get("/search")
    assert response.status_code == 200
