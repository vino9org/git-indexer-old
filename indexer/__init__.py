import os
import sqlite3
import sys
import traceback
from datetime import datetime
from typing import Optional, cast

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

from .models import Base, Commit, CommittedFile, ensure_author, ensure_repository
from .stats import __STATS_SQL__


class Indexer:
    # TODO: add proper exception catching and printing mechanism

    def __init__(self, uri: Optional[str] = None, db_file: Optional[str] = None, echo: bool = False):
        env_uri = os.environ.get("SQLALCHEMY_DATABASE_URI")
        if uri:
            self.uri = uri
            self.is_mem_db = False
        elif env_uri:
            self.uri = env_uri
            self.is_mem_db = False
        else:
            self.uri = "sqlite:///:memory:"
            self.is_mem_db = True

        self.db_file = db_file
        self.engine = create_engine(self.uri, echo=echo)
        self.session = Session(self.engine)

        if self.is_mem_db and db_file and os.path.isfile(db_file):
            disk_db = sqlite3.connect(db_file)
            disk_db.backup(cast(sqlite3.dbapi2.Connection, self.session.connection().connection.driver_connection))
            log(f"loaded database {db_file} into memory")

        Base.metadata.create_all(self.engine)

    def close(self):
        self.session.close()

        if self.is_mem_db and self.db_file:
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
        n_branch_updates, n_new_commits = 0, 0

        try:
            log(f"starting to index {display_url(clone_url)}")
            start_t = datetime.now()
            repo = ensure_repository(self.session, clone_url=clone_url, repo_type=git_repo_type)

            # use list comprehension to force loading of commits
            old_commits = [commit for commit in repo.commits]  # noqa: C416
            old_hashes = [commit.sha for commit in old_commits]

            url = patch_ssh_gitlab_url(clone_url)  # kludge: workaround for some unfortunate ssh setup
            for commit in PyDrillerRepository(url, include_refs=True, include_remotes=True).traverse_commits():
                # impose some timeout to avoid spending tons of time on very large repositories
                if (datetime.now() - start_t).seconds > timeout:
                    print(f"### indexing not done after {timeout} seconds, aborting {display_url(clone_url)}")
                    break

                if commit.hash in old_hashes:
                    # we've seen this commit before, just compare branches and update
                    # if needed
                    old_commit = [item for item in old_commits if item.sha == commit.hash][0]
                    new_branches = normalize_branches(commit.branches)
                    if new_branches != old_commit.branches:
                        old_commit.branches = new_branches
                        self.session.add(old_commit)
                        n_branch_updates += 1
                else:
                    # it is a new commit
                    new_commit = self._new_commit_(commit)
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
                print(f"### unable to save commit {commit.hash} => {str(e)}\n{exc}", file=sys.stderr)
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
