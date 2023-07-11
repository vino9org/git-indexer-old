import os
import sqlite3
import sys
import traceback
from datetime import datetime
from typing import Optional

from flask_sqlalchemy import SQLAlchemy
from git.exc import GitCommandError
from pydriller import Repository as PyDrillerRepository
from pydriller.domain.commit import Commit as PyDrillerCommit
from sqlalchemy import create_engine
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from utils import (
    display_url,
    log,
    normalize_branches,
    patch_ssh_gitlab_url,
    should_exclude_from_stats,
)

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
    def __init__(
        self,
        uri: Optional[str] = None,
        db_file: str = "",
        echo: bool = False,
        flask_db: Optional[SQLAlchemy] = None,
    ):
        if flask_db:
            self._init_from_flask_db(flask_db)
            self.db_file = ""
        else:
            env_uri = os.environ.get("SQLALCHEMY_DATABASE_URI")
            if uri:
                self.uri = uri
            elif env_uri:
                self.uri = env_uri
            else:
                self.uri = "sqlite:///:memory:"

            self._init_db_(self.uri, db_file, echo)

        Base.metadata.create_all(self.engine)

    def _init_db_(self, uri: str, db_file: str, echo: bool = False):
        self.is_mem_db = ":memory:" in self.uri
        self.db_file = db_file
        self.engine = create_engine(self.uri, echo=echo)
        self.session = Session(self.engine)

        if self.is_mem_db and db_file and os.path.isfile(db_file):
            disk_db = sqlite3.connect(db_file)
            disk_db.backup(self.session.connection().connection.driver_connection)  # type: ignore   #it works...
            log(f"loaded database {db_file} into memory")

    def _init_from_flask_db(self, flask_db: SQLAlchemy):
        """
        use a DB object from Flask to initialize the indexer,
        in order to share the database with Flask application.
        Since flask-sqlalchemy initializes the database independently,
        we need to let it do all its initialization first, the extract
        engine from it.
        """
        self.engine = flask_db.engines[None]
        if self.engine is None:
            raise ValueError("cannot find engine from flask db")
        self.uri = str(self.engine.engine.url)
        self.is_mem_db = ":memory:" in self.uri
        self.session = Session(self.engine)

    def close(self):
        self.session.close()

        if self.is_mem_db and self.db_file:
            self._export_db_(self.db_file)

    def _export_db_(self, dbf: str):
        # export database to file
        # write to temp file first then rename to avoid potentially corrupting the database
        tmp_file = dbf + ".new"
        file_conn = sqlite3.connect(tmp_file)
        self.session.connection().connection.driver_connection.backup(file_conn)  # type: ignore   #it works...
        file_conn.close()

        if dbf and os.path.exists(dbf):
            os.unlink(dbf)
        os.rename(tmp_file, dbf)
        log(f"saved database to {dbf}")

    def index_repository(
        self, clone_url: str, git_repo_type: str = "", show_progress: bool = False, timeout: int = 28800
    ) -> int:
        n_branch_updates, n_new_commits = 0, 0

        try:
            log(f"starting to index {display_url(clone_url)}")
            start_t = datetime.now()
            repo = ensure_repository(self.session, clone_url=clone_url, repo_type=git_repo_type)

            # use list comprehension to force loading of commits
            old_commits = {}
            for commit in repo.commits:
                old_commits[commit.sha] = commit

            url = patch_ssh_gitlab_url(clone_url)  # kludge: workaround for some unfortunate ssh setup
            for git_commit in PyDrillerRepository(url, include_refs=True, include_remotes=True).traverse_commits():
                # impose some timeout to avoid spending tons of time on very large repositories
                if (datetime.now() - start_t).seconds > timeout:
                    print(f"### indexing not done after {timeout} seconds, aborting {display_url(clone_url)}")
                    break

                git_commit_hash = git_commit.hash
                if git_commit_hash in old_commits:
                    # we've seen this commit before, just compare branches and update
                    # if needed
                    old_commit = old_commits[git_commit_hash]
                    new_branches = normalize_branches(git_commit.branches)
                    if new_branches != old_commit.branches:
                        old_commit.branches = new_branches
                        self.session.add(old_commit)
                        n_branch_updates += 1
                else:
                    # new commit in this repo, check if the repo is already exist in another repo
                    new_commit = load_commit(self.session, git_commit_hash)
                    if new_commit is None:
                        new_commit = self._new_commit_(git_commit)
                    repo.commits.append(new_commit)
                    n_new_commits += 1

                nn = n_new_commits + n_branch_updates
                if nn > 0 and nn % 200 == 0 and show_progress:
                    log(f"indexed {n_new_commits:5,} new commits and {n_branch_updates:5,} branch updates")

            repo.last_indexed_at = datetime.now().astimezone().isoformat(timespec="seconds")
            self.session.add(repo)

            try:
                self.session.commit()
            except Exception as e:
                exc = traceback.format_exc()
                print(f"### unable to save commit {git_commit_hash} => {str(e)}\n{exc}", file=sys.stderr)
                self.session.rollback()

            if (n_new_commits + n_branch_updates) > 0:
                log(
                    f"indexed {n_new_commits:5,} new commits and {n_branch_updates:5,} branch updates in the repository"
                )

            return n_new_commits + n_branch_updates

        except GitCommandError as e:
            print(f"{e._cmdline} returned {e.stderr} for {clone_url}")
        except DBAPIError as e:
            print(f"{e.statement} returned {e._message}")
        except Exception as e:
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
            branches=normalize_branches(commit.branches),
            n_lines=commit.lines,
            n_files=commit.files,
            n_insertions=commit.insertions,
            n_deletions=commit.deletions,
            # comment to save some time. metrics not used for now
            # dmm_unit_size=commit.dmm_unit_size,
            # dmm_unit_complexity=commit.dmm_unit_complexity,
            # dmm_unit_interfacing=commit.dmm_unit_interfacing,
            created_at=commit.committer_date.isoformat(),
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
