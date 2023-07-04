import os

import pytest
from constants import __TEST_GITHUB_REPO___, __TEST_GITLAB_REPO___

from indexer import index_repository


def test_index_github_repo():
    assert index_repository(f"https://github.com/{__TEST_GITHUB_REPO___}.git") > 3


@pytest.mark.skipif(os.environ.get("GITLAB_TOKEN") is None, reason="gitlab token not available")
def test_index_gitlab_repo():
    assert index_repository(f"https://gitlab.com/vino9/{__TEST_GITLAB_REPO___}") > 0


def test_index_local_repo(local_repo):
    assert (
        index_repository(
            local_repo + "/repo1",
        )
        > 3
    )
