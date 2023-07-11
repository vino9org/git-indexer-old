import os
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, List, Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Table,
)
from sqlalchemy.orm import Mapped, Session, mapped_column, registry, relationship
from sqlalchemy.orm.decl_api import DeclarativeMeta

from utils import clone_to_browse_url

_REPO_TYPES_ = ["gitlab", "gitlab_private", "github", "bitbucket", "bitbucket_private", "local", "other"]


mapper_registry = registry()


class Base(metaclass=DeclarativeMeta):
    __abstract__ = True
    registry = mapper_registry
    metadata = mapper_registry.metadata

    __init__ = mapper_registry.constructor


repo_to_commit_table = Table(
    "repo_to_commits",
    Base.metadata,
    Column("repo_id", ForeignKey("repositories.id"), primary_key=True),
    Column("commit_id", ForeignKey("commits.sha"), primary_key=True),
)


@dataclass
class Repository(Base):
    __tablename__ = "repositories"

    id: Mapped[int] = mapped_column(primary_key=True)  # noqa: A003,VNE003
    repo_type: Mapped[str] = mapped_column(String(20))
    repo_name: Mapped[str] = mapped_column(String(128))
    repo_group: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    component: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    clone_url: Mapped[str] = mapped_column(String(256))
    browse_url: Mapped[str] = mapped_column(String(256))
    include_in_stats: Mapped[bool] = mapped_column(Boolean, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_indexed_at: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    commits: Mapped[List["Commit"]] = relationship(secondary=repo_to_commit_table, back_populates="repos")

    # create a constructor to set browse_url based on clone_url
    def __init__(self, **kw: Any) -> None:
        super().__init__(**kw)

        if self.id:
            # already initialized, e.g. loaded from database
            # skip the rest of the initialization
            return

        if self.repo_type and self.repo_type not in _REPO_TYPES_:
            raise ValueError(f"repo_type must be one of {_REPO_TYPES_}")

        # try to determine repo_type is not provided
        if not self.repo_type:
            if self.clone_url.startswith("http") or self.clone_url.startswith("git@"):
                # remote repo
                if "gitlab" in self.clone_url:
                    self.repo_type = "gitlab"
                elif "github.com" in self.clone_url:
                    self.repo_type = "github"
                elif "bitbucket.com" in self.clone_url:
                    self.repo_type = "bitbucket"
            else:
                self.repo_type = "local"

        if self.repo_type == "local":
            self.browse_url = "http://localhost:9000/gitweb/"
        else:
            self.browse_url = clone_to_browse_url(self.clone_url)

        name = os.path.basename(self.clone_url)  # works for both http and git@ style url
        self.repo_name = re.sub(r".git$", "", name)

    def __repr__(self) -> str:
        return f"Repository(id={self.id!r}, url={self.browse_url!r}, clone_url={self.clone_url!r})"

    @property
    def url_for_commit(self) -> str:
        """return the url that display the commit details"""
        if self.repo_type == "github":
            return f"{self.browse_url}/commit"
        elif self.repo_type.startswith("gitlab"):
            return f"{self.browse_url}/-/commit"
        elif self.repo_type.startswith("bitbucket"):
            return f"{self.browse_url}/commits"
        else:
            return ""


@dataclass
class Commit(Base):
    __tablename__ = "commits"

    sha: Mapped[str] = mapped_column(primary_key=True)
    branches: Mapped[str] = mapped_column(String(1024), default="[]")
    message: Mapped[str] = mapped_column(String(2048), default="")
    created_at: Mapped[str] = mapped_column(String(32))
    created_ts: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # metrics by pydriller
    is_merge: Mapped[bool] = mapped_column(Boolean, default=False)
    n_lines: Mapped[int] = mapped_column(Integer, default=0)
    n_files: Mapped[int] = mapped_column(Integer, default=0)
    n_insertions: Mapped[int] = mapped_column(Integer, default=0)
    n_deletions: Mapped[int] = mapped_column(Integer, default=0)
    dmm_unit_size: Mapped[float] = mapped_column(Float, default=0.0)
    dmm_unit_complexity: Mapped[float] = mapped_column(Float, default=0.0)
    dmm_unit_interfacing: Mapped[float] = mapped_column(Float, default=0.0)
    # should be populated from committed_files
    n_lines_changed: Mapped[int] = mapped_column(Integer, default=0)
    n_lines_ignored: Mapped[int] = mapped_column(Integer, default=0)
    n_files_changed: Mapped[int] = mapped_column(Integer, default=0)
    n_files_ignored: Mapped[int] = mapped_column(Integer, default=0)

    # relationships
    author_id: Mapped[int] = mapped_column(ForeignKey("authors.id"))
    author: Mapped["Author"] = relationship("Author", back_populates="commits")

    repos: Mapped[List["Repository"]] = relationship(secondary=repo_to_commit_table, back_populates="commits")

    files: Mapped[List["CommittedFile"]] = relationship("CommittedFile", back_populates="commit")

    def __repr__(self) -> str:
        return f"commits(id={self.sha!r} in message={self.message[:20]!r})"


@dataclass
class CommittedFile(Base):
    __tablename__ = "committed_files"

    id: Mapped[int] = mapped_column(primary_key=True)  # noqa: A003,VNE003
    commit_sha: Mapped[str] = mapped_column(String(40))
    change_type: Mapped[str] = mapped_column(String(16), default="UNKNOWN")
    file_path: Mapped[str] = mapped_column(String(256))
    file_name: Mapped[str] = mapped_column(String(128))
    file_type: Mapped[str] = mapped_column(String(128))

    # line metrics from Pydiller
    n_lines_added: Mapped[int] = mapped_column(Integer, default=0)
    n_lines_deleted: Mapped[int] = mapped_column(Integer, default=0)
    n_lines_changed: Mapped[int] = mapped_column(Integer, default=0)  # n_lines_added + n_lines_deleted
    n_lines_of_code: Mapped[int] = mapped_column(Integer, default=0)
    # metho metrics from pydriller
    n_methods: Mapped[int] = mapped_column(Integer, default=0)
    n_methods_changed: Mapped[int] = mapped_column(Integer, default=0)
    is_on_exclude_list: Mapped[bool] = mapped_column(Boolean, default=False)
    is_superfluous: Mapped[bool] = mapped_column(Boolean, default=False)

    # relationships
    commit_id: Mapped[int] = mapped_column(ForeignKey("commits.sha"))
    commit: Mapped["Commit"] = relationship("Commit", back_populates="files")

    def __init__(self, **kw: Any) -> None:
        super().__init__(**kw)

        if self.id:
            return

        main, ext = os.path.splitext(self.file_path)
        if main.startswith("."):
            self.file_type = "hiden"
        elif ext != "":
            self.file_type = ext[1:].lower()
        else:
            self.file_type = "generic"

    def __repr__(self) -> str:
        return f"commits(id={self.id!r} in commit {self.commit_sha!r})"


@dataclass
class Author(Base):
    __tablename__ = "authors"

    id: Mapped[int] = mapped_column(primary_key=True)  # noqa: A003,VNE003
    name: Mapped[str] = mapped_column(String(128))
    email: Mapped[str] = mapped_column(String(1024))
    real_name: Mapped[str] = mapped_column(String(128))
    real_email: Mapped[str] = mapped_column(String(1024))
    company: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    team: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    group: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # relationships
    commits: Mapped[List["Commit"]] = relationship("Commit", back_populates="author")

    def __repr__(self) -> str:
        return f"Authro(id={self.id!r}, name={self.name}, email={self.email!r})"


def ensure_repository(session: Session, clone_url: str, repo_type: str) -> Repository:
    repo = session.query(Repository).filter(Repository.clone_url == clone_url).one_or_none()
    if repo is None:
        repo = Repository(clone_url=clone_url, repo_type=repo_type)
        session.add(repo)
        session.commit()
    return repo


def ensure_author(session: Session, name: str, email: str) -> Author:
    author = session.query(Author).filter(Author.email == email and Author.name == name).one_or_none()
    if author is None:
        author = Author(name=name, email=email, real_name=name, real_email=email)
        session.add(author)
        session.commit()
    return author


def load_commit(session: Session, sha: str) -> Optional[Commit]:
    return session.query(Commit).filter(Commit.sha == sha).one_or_none()
