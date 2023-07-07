from datetime import datetime

from sqlalchemy import select

from indexer.models import (
    Author,
    Commit,
    CommittedFile,
    Repository,
    ensure_author,
    ensure_repository,
    load_commit,
)


def test_models(session):
    author = session.scalars(select(Author).where(Author.name == "me")).first()
    assert author.id is not None

    commit = session.scalars(select(Commit).where(Commit.sha == "feb3a2837630c0e51447fc1d7e68d86f964a8440")).first()
    assert commit is not None
    # test commit to author relation
    assert commit.author_id == author.id
    # test commit to repo many-to-many relation
    assert len(commit.repos) == 2
    assert commit.repos[0].browse_url == "https://github.com/super/repo"

    commit2 = session.scalars(select(Commit).where(Commit.sha == "ee474544052762d314756bb7439d6dab73221d3d")).first()
    assert commit2 is not None and len(commit2.repos) == 1

    # test repo to commit many-to-many relation
    repo = session.scalars(select(Repository).where(Repository.clone_url == "git@github.com:super/repo.git")).first()
    assert repo is not None
    assert len(repo.commits) == 2


def test_ensure_repository(session):
    all_repos = session.scalars(select(Repository)).all()
    params = {
        "clone_url": "git@my_company.com:fancy_project/stupid_code.git",
        "repo_type": "gitlab_private",
    }

    # run 1st time creates a new record
    repo = ensure_repository(session, **params)
    assert repo.id not in [r.id for r in all_repos]
    assert repo.browse_url == "https://my_company.com/fancy_project/stupid_code"

    # run 2nd time will return the same record
    repo2 = ensure_repository(session, **params)
    assert repo2.id == repo.id


def test_ensure_author(session):
    all_authors = session.scalars(select(Author)).all()

    params = {
        "name": "Linus Torvalds",
        "email": "torvalds@osdl.org",
    }

    # run 1st time creates a new record
    author = ensure_author(session, **params)
    assert author.id not in [r.id for r in all_authors]

    # run 2nd time will return the same record
    author2 = ensure_author(session, **params)
    assert author2.id == author.id


def test_typical_indexing_flow(session):
    """Test typical indexing flow"""
    # 1. create new repo
    repo1 = ensure_repository(session, clone_url="git@gitlab.com:super/repo.git", repo_type="gitlab")

    # 2. create new author
    author = ensure_author(session, name="dummy", email="dummy@nocode.com")

    sha = "feb3a2837630c0e51447fc1d7e68d86f964a8440"
    commit = load_commit(session, sha)
    if load_commit(session, sha) is None:
        commit = Commit(sha=sha, message="initial commit", author=author, created_at=datetime.now())
        if repo1 not in commit.repos:
            commit.repos = [repo1]

        new_file_1 = CommittedFile(
            commit_sha=sha,
            file_path="README.md",
            file_name="README.md",
            change_type="ADD",
        )

        new_file_2 = CommittedFile(
            commit_sha=sha,
            file_path="package.json",
            file_name="package.json",
            change_type="UPDATE",
        )

        commit.files += [new_file_1, new_file_2]

    session.add(commit)
    session.commit()

    # same commit from a different repo
    commit = load_commit(session, sha)
    assert commit is not None and commit.sha == sha

    repo2 = ensure_repository(session, clone_url="git@github.com:facny/repo.git", repo_type="github")
    if commit not in repo2.commits:
        repo2.commits += [commit]

    session.add(repo2)
    session.commit()
