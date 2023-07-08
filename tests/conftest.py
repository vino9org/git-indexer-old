import os
import shutil
import sqlite3
import sys
import tempfile
import zipfile
from datetime import datetime

import pytest
from dotenv import find_dotenv, load_dotenv

cwd = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(f"{cwd}/.."))

from indexer import Indexer  # noqa: E402   sys.path should be set prior to import
from indexer.models import Author, Commit, Repository  # noqa: E402

load_dotenv(find_dotenv(".env.test"))


def seed_data(session):
    me = Author(name="me", email="mini@me", real_name="me", real_email="mini@me")

    commit1 = Commit(sha="feb3a2837630c0e51447fc1d7e68d86f964a8440", author=me, created_at=datetime.now())
    commit2 = Commit(sha="ee474544052762d314756bb7439d6dab73221d3d", author=me, created_at=datetime.now())
    commit3 = Commit(sha="e2c8b79813b95c93e5b06c5a82e4c417d5020762", author=me, created_at=datetime.now())

    repo1 = Repository(clone_url="git@github.com:super/repo.git", repo_type="github", commits=[commit1, commit2])
    repo2 = Repository(clone_url="https://gitlab.com/dummy/repo.git", repo_type="gitlab", commits=[commit1, commit3])

    session.add_all([me, repo1, repo2])
    session.commit()


@pytest.fixture(scope="session")
def indexer(tmpdir_factory):
    tmp_dir = tmpdir_factory.mktemp("git-indexer")
    db_file = tmp_dir / "tmp.db"
    db = sqlite3.connect(db_file)
    db.close()
    os.environ["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_file}"
    indexer = Indexer()

    yield indexer

    indexer.close()
    shutil.rmtree(tmp_dir)


@pytest.fixture(scope="session")
def session(indexer):
    seed_data(indexer.session)
    yield indexer.session


@pytest.fixture
def local_repo(tmp_path):
    repo_base = tempfile.mkdtemp(dir=tmp_path)
    zip_file_path = os.path.abspath(f"{cwd}/data/test_repos.zip")
    with zipfile.ZipFile(zip_file_path, "r") as zip_ref:
        zip_ref.extractall(repo_base)

    yield repo_base

    shutil.rmtree(repo_base)
