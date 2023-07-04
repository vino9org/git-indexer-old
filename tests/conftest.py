import os
import shutil
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

    commit1 = Commit(sha="123123123", author=me, created_at=datetime.now())
    commit2 = Commit(sha="12fed3433", author=me, created_at=datetime.now())
    commit3 = Commit(sha="12fed3fff", author=me, created_at=datetime.now())

    repo1 = Repository(clone_url="git@github.com:super/repo.git", repo_type="github", commits=[commit1, commit2])
    repo2 = Repository(clone_url="https://gitlab.com/dummy/repo.git", repo_type="gitlab", commits=[commit1, commit3])

    session.add_all([me, repo1, repo2])
    session.commit()


@pytest.fixture(scope="session")
def indexer():
    indexer = Indexer("sqlite:///:memory:")
    yield indexer


@pytest.fixture(scope="session")
def session(indexer):
    seed_data(indexer.session)
    yield indexer.session


@pytest.fixture
def local_repo(tmp_path):
    temp_dir = tempfile.mkdtemp(dir=tmp_path)
    zip_file_path = os.path.abspath(f"{cwd}/data/repo1.zip")
    with zipfile.ZipFile(zip_file_path, "r") as zip_ref:
        zip_ref.extractall(temp_dir)

    yield temp_dir

    shutil.rmtree(temp_dir)
