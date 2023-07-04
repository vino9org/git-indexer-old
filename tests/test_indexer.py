import os

import pytest
from constants import __TEST_GITHUB_REPO___, __TEST_GITLAB_REPO___


def test_index_github_repo(indexer):
    assert indexer.index_repository(f"https://github.com/{__TEST_GITHUB_REPO___}.git") > 3


@pytest.mark.skipif(os.environ.get("GITLAB_TOKEN") is None, reason="gitlab token not available")
def test_index_gitlab_repo(indexer):
    assert indexer.index_repository(f"https://gitlab.com/vino9/{__TEST_GITLAB_REPO___}") > 0


def test_index_local_repo(indexer, local_repo):
    assert (
        indexer.index_repository(
            local_repo + "/repo1",
        )
        > 3
    )
