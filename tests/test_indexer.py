import os

import pytest
from constants import __TEST_GITHUB_REPO___, __TEST_GITLAB_REPO___
from sqlalchemy import text

from indexer.models import ensure_repository


def test_index_github_repo(indexer):
    assert indexer.index_repository(f"https://github.com/{__TEST_GITHUB_REPO___}.git") > 3


@pytest.mark.skipif(os.environ.get("GITLAB_TOKEN") is None, reason="gitlab token not available")
def test_index_gitlab_repo(indexer):
    assert indexer.index_repository(f"https://gitlab.com/vino9/{__TEST_GITLAB_REPO___}") > 0


def test_index_local_repo(indexer, local_repo):
    """
    there're 2 test repos
    repo1 has 2 commits
    repo1_clone is a clone of repo1, then add 1 more commits, so totaly 3 commits
    empty_repo is empty, no commit after git init.
    """
    session = indexer.session

    repo1 = local_repo + "/repo1"
    assert indexer.index_repository(repo1) == 2
    repo1_sha = repo_hashes(session, repo1)
    assert len(repo1_sha) == 2

    repo1_clone = local_repo + "/repo1_clone"
    assert indexer.index_repository(repo1_clone) == 3
    repo1_clone_sha = repo_hashes(session, repo1_clone)
    assert len(repo1_clone_sha) == 3

    empty_repo = local_repo + "/empty_repo"
    assert indexer.index_repository(empty_repo) == 0

    assert all(sha in repo1_clone_sha for sha in repo1_sha)
    assert 5 == get_row_count_from_join_table(session, repo1_clone_sha)


def repo_hashes(session, repo_url):
    repo = ensure_repository(session, repo_url, "local")
    hashes = [c.sha for c in repo.commits]
    # does a unique then return. technically not needed
    return list(set(hashes))


def get_row_count_from_join_table(session, sha_lst):
    in_clause = "(" + ",".join(["'" + sha + "'" for sha in sha_lst]) + ")"
    result = session.execute(text(f"select count(*) from repo_to_commits where commit_id in {in_clause}")).fetchone()
    return result[0] if result is not None else 0
