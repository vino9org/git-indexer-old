import os
import sqlite3
import sys
import traceback
from datetime import datetime
from typing import Optional, cast

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


class Indexer:
    # TODO: add proper exception catching and printing mechanism

    def __init__(self, uri: Optional[str] = None, db_file: Optional[str] = None, echo: bool = False):
        env_uri = os.environ.get("SQLALCHEMY_DATABASE_URI")
        if uri:
            self.uri = uri
            self.is_mem_db = False
        elif env_uri:
            self.db_uri = env_uri
            self.is_mem_db = False
        else:
            self.uri = "sqlite:///:memory:"
            self.is_mem_db = True

        self.engine = create_engine(self.uri, echo=echo)
        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine)

        if self.is_mem_db and db_file and os.path.isfile(db_file):
            disk_db = sqlite3.connect(db_file)
            disk_db.backup(cast(sqlite3.dbapi2.Connection, self.session.connection().connection.driver_connection))
            self.db_file = db_file
            log(f"loaded database {self.db_file} into memory")

    def close(self):
        self.session.close()

        if self.is_mem_db:
            # export database to file
            # write to temp file first then rename to avoid potentially corrupting the database
            tmp_file = self.db_file + ".new"
            file_conn = sqlite3.connect(tmp_file)
            self.session.connection().connection.driver_connection.backup(file_conn)
            file_conn.close()

            if os.path.exists(self.db_file):
                os.unlink(self.db_file)
            os.rename(tmp_file, self.db_file)
            log(f"saved database to {self.db_file}")

    def index_repository(
        self, clone_url: str, git_repo_type: str = "", show_progress: bool = False, timeout: int = 28800
    ) -> int:
        processed = 0
        try:
            log(f"starting to index {display_url(clone_url)}")

            repo = ensure_repository(self.session, clone_url=clone_url, repo_type=git_repo_type)
            old_commits = [commit.sha for commit in repo.commits]
            start_t = datetime.now()

            for commit in PyDrillerRepository(clone_url, include_refs=True, include_remotes=True).traverse_commits():
                if commit.hash in old_commits:
                    continue

                if (datetime.now() - start_t).seconds > timeout:
                    print(f"### indexing not done after {timeout} seconds, aborting {display_url(clone_url)}")
                    continue

                git_commit = load_commit(self.session, commit.hash)
                if not git_commit:
                    git_commit = self._new_commit_(commit)

                repo.commits.append(git_commit)

                processed += 1
                if processed % 200 == 0 and show_progress:
                    log(f"Indexed {processed:7,} commits")

            repo.last_indexed_at = datetime.now()
            self.session.add(repo)

            try:
                self.session.commit()
            except Exception as e:
                exc = traceback.format_exc()
                print(f"### unable to save commit {commit.hash} => {str(e)}\n{exc}", file=sys.stderr)
                self.session.rollback()

            if processed > 0:
                log(f"Indexed {processed:7,} commits in the repository")

            return processed

        except DBAPIError as e:
            exc = traceback.format_exc()
            print(f"Exception indexing repository {clone_url} => {str(e)}\n{exc}")
            return 0

    def update_commit_stats(self) -> None:
        """update stats at commit level"""
        log("updating commit stats")
        for statement in __STATS_SQL__:
            try:
                self.session.execute(statement)
                self.session.commit()
            except DBAPIError as e:
                self.session.rollback()
                exc = traceback.format_exc()
                print(f"Exception execute statement {statement} => {str(e)}\n{exc}")

    def _new_commit_(self, commit: PyDrillerCommit) -> Commit:
        author = ensure_author(self.session, commit.committer.name.lower(), commit.committer.email.lower())

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
