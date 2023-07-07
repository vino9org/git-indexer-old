def test_search_page(session):
    from gui import app

    response = app.test_client().get("/search")
    assert response.status_code == 200


def test_search_by_commit(session):
    # import gui model will initialize the sqlalchemy
    # so we'll let fixture session intialize first to populate test data
    from gui import app

    sha = "feb3a2837630c0e51447fc1d7e68d86f964a8440"
    with app.test_client() as client:
        response = client.post(
            "/search",
            data={"query": sha},
            follow_redirects=True,
            content_type="application/x-www-form-urlencoded",
        )
        assert response.status_code == 200
        assert bytes(sha, "utf-8") in response.data


def test_search_by_email(session):
    # import gui model will initialize the sqlalchemy
    # so we'll let fixture session intialize first to populate test data
    from gui import app

    sha = "feb3a2837630c0e51447fc1d7e68d86f964a8440"
    with app.test_client() as client:
        response = client.post(
            "/search",
            data={"query": "mini@me"},
            follow_redirects=True,
            content_type="application/x-www-form-urlencoded",
        )
        assert response.status_code == 200
        assert bytes(sha, "utf-8") in response.data


def test_search_by_repo_name(session):
    # import gui model will initialize the sqlalchemy
    # so we'll let fixture session intialize first to populate test data
    from gui import app

    sha = "feb3a2837630c0e51447fc1d7e68d86f964a8440"
    with app.test_client() as client:
        response = client.post(
            "/search",
            data={"query": "repo "},
            follow_redirects=True,
            content_type="application/x-www-form-urlencoded",
        )
        assert response.status_code == 200
        assert bytes(sha, "utf-8") in response.data
