import os
import sqlite3
import sys
import traceback
from datetime import datetime
from typing import cast

from pydriller import Repository as PyDrillerRepository
from pydriller.domain.commit import Commit as PyDrillerCommit
from sqlalchemy import create_engine
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from utils import display_url, log, should_exclude_from_stats

from .models import (
    Base,
    Commit,
    CommittedFile,
    ensure_author,
    ensure_repository,
    load_commit,
)
from .stats import __STATS_SQL__

engine = create_engine("sqlite:///:memory:", echo=False)
session = Session(bind=engine)
Base.metadata.create_all(engine)


def new_commit(commit: PyDrillerCommit) -> Commit:
    author = ensure_author(session, commit.committer.name.lower(), commit.committer.email.lower())

    git_commit = Commit(
        sha=commit.hash,
        message=commit.msg[:2048],  # some commits has super long message, e.g. squash merge
        author=author,
        is_merge=commit.merge,
        branches=",".join(list(commit.branches))[:1024],  # this attribute may not be immutable, how useful is it?
        n_lines=commit.lines,
        n_files=commit.files,
        n_insertions=commit.insertions,
        n_deletions=commit.deletions,
        # comment to save some time. metrics not used for now
        # dmm_unit_size=commit.dmm_unit_size,
        # dmm_unit_complexity=commit.dmm_unit_complexity,
        # dmm_unit_interfacing=commit.dmm_unit_interfacing,
        created_at=commit.committer_date,
    )

    for mod in commit.modified_files:
        file_path = mod.new_path or mod.old_path
        flag = should_exclude_from_stats(file_path)
        new_file = CommittedFile(
            commit_sha=commit.hash,
            change_type=str(mod.change_type).split(".")[1],  # enum ModificationType.ADD => "ADD"
            file_path=file_path,
            file_name=mod.filename,
            n_lines_added=mod.added_lines,
            n_lines_deleted=mod.deleted_lines,
            n_lines_changed=mod.added_lines + mod.deleted_lines,
            n_lines_of_code=mod.nloc,
            n_methods=len(mod.methods),
            n_methods_changed=len(mod.changed_methods),
            is_on_exclude_list=flag,
            is_superfluous=flag,
        )
        git_commit.files.append(new_file)

    return git_commit


def index_repository(clone_url: str, git_repo_type: str = "", show_progress: bool = False, timeout: int = 28800) -> int:
    processed = 0
    try:
        log(f"starting to index {display_url(clone_url)}")

        repo = ensure_repository(session, clone_url=clone_url, repo_type=git_repo_type)
        old_commits = [commit.sha for commit in repo.commits]
        start_t = datetime.now()

        for commit in PyDrillerRepository(clone_url, include_refs=True, include_remotes=True).traverse_commits():
            if commit.hash in old_commits:
                continue

            if (datetime.now() - start_t).seconds > timeout:
                print(f"### indexing not done after {timeout} seconds, aborting {display_url(clone_url)}")
                continue

            git_commit = load_commit(session, commit.hash)
            if not git_commit:
                git_commit = new_commit(commit)

            repo.commits.append(git_commit)

            processed += 1
            if processed % 200 == 0 and show_progress:
                log(f"Indexed {processed:7,} commits")

        repo.last_indexed_at = datetime.now()
        session.add(repo)

        try:
            session.commit()
        except Exception as e:
            exc = traceback.format_exc()
            print(f"### unable to save commit {commit.hash} => {str(e)}\n{exc}", file=sys.stderr)
            session.rollback()

        if processed > 0:
            log(f"Indexed {processed:7,} commits in the repository")

        return processed

    except DBAPIError as e:
        exc = traceback.format_exc()
        print(f"Exception indexing repository {clone_url} => {str(e)}\n{exc}")
        return 0


def update_commit_stats() -> None:
    """update stats at commit level"""
    log("updating commit stats")
    for statement in __STATS_SQL__:
        try:
            session.execute(statement)
            session.commit()
        except DBAPIError as e:
            session.rollback()
            exc = traceback.format_exc()
            print(f"Exception execute statement {statement} => {str(e)}\n{exc}")


def db_restore(db_file: str) -> None:
    disk_db = sqlite3.connect(db_file)
    disk_db.backup(cast(sqlite3.dbapi2.Connection, session.connection().connection.driver_connection))
    log(f"loaded database {db_file} into memory")


def db_export(db_file):
    """
    export database to file
    write to temp file first then rename to avoid potentially corrupting the database
    """
    tmp_file = db_file + ".new"
    file_conn = sqlite3.connect(tmp_file)
    session.connection().connection.driver_connection.backup(file_conn)
    file_conn.close()

    if os.path.exists(db_file):
        os.unlink(db_file)
    os.rename(tmp_file, db_file)
    log(f"exported data to {db_file}")


# TODO: add proper exception catching and printing mechanism
