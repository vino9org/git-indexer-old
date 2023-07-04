import argparse
import os
import re
import shlex
import subprocess
import sys
from functools import partial
from typing import Iterable

from dotenv import load_dotenv

from indexer import Indexer
from utils import (
    enumerate_github_repos,
    enumerate_gitlab_repos,
    enumerate_local_repos,
    log,
    match_any,
    timestamp,
    upload_file,
)

load_dotenv()


def enumberate_from_file(source_file: str, query: str) -> Iterable[str]:
    with open(source_file, "r") as f:
        for line in f.readlines():
            line = line.strip()
            if not line.startswith("#") and len(line) > 6:
                yield line.strip()


def run(command: str, dry_run: bool) -> int:
    cwd = os.getcwd()
    print(f"pwd={cwd}\n{command}")

    if dry_run:
        return True

    ret = subprocess.call(shlex.split(command))
    if ret == 0:
        return True
    else:
        print(f"*** return code {ret}", file=sys.stderr)
        return False


def mirror_repo(clone_url: str, dest_path: str, dry_run: bool = False, overwrite: bool = False) -> int:
    """
    create a local mirror (as a bare repo) of a remote repo
    """
    path = clone_url.split(":")[1]
    parent_dir = os.path.abspath(os.path.expanduser(dest_path)) + "/" + os.path.dirname(path)
    repo_dir = os.path.basename(path)

    cwd = os.getcwd()
    try:
        if os.path.isdir(parent_dir):
            os.chdir(parent_dir)
            if os.path.isdir(f"{repo_dir}/objects"):
                os.chdir(repo_dir)
                return run("git fetch --prune", dry_run)
            else:
                if os.path.isdir(repo_dir):
                    if overwrite:
                        run(f"rm -rf {repo_dir}", dry_run)
                    else:
                        print(f"*** {path}.git exists, skipping...")
                        return False
        else:
            run(f"mkdir -p {parent_dir}", dry_run)

        if not dry_run:
            os.chdir(parent_dir)
        return run(f"git clone --mirror {clone_url}", dry_run)

    finally:
        os.chdir(cwd)


def run_mirror(args: argparse.Namespace) -> None:
    if args.source == "gitlab":
        enumerator = partial(enumerate_gitlab_repos)
    elif args.source == "github":
        enumerator = partial(enumerate_github_repos)
    else:
        print("don't nkow how to mirror local repos")
        return None

    for repo_url in enumerator(args.query):
        if match_any(repo_url, args.filter):
            print(f"Mirroring {repo_url} to {args.output}")
            mirror_repo(repo_url, args.output, args.dry_run, args.overwrite)


def run_indexer(args: argparse.Namespace) -> None:
    # the sqlite3 database this program needs will reside in memory
    # for performance reason as well as ability to run in serverless environment
    # we'll load the database from disk if it exists
    # after indexing is done we'll save the database in memory back to disk
    n_repos, n_commits = 0, 0

    indexer = Indexer(db_file=os.path.expanduser(args.db))

    if args.source == "gitlab":
        enumerator = partial(enumerate_gitlab_repos)
    elif args.source == "github":
        enumerator = partial(enumerate_github_repos)
    elif args.source == "local":
        enumerator = partial(enumerate_local_repos)
    elif args.source == "list":
        enumerator = partial(enumberate_from_file, args.query)
    else:
        print(f"don't know how to index {args.source}")
        return

    for repo_url in enumerator(args.query):
        if match_any(repo_url, args.filter):
            if not args.dry_run:
                n_commits += indexer.index_repository(repo_url, args.source, show_progress=True)
                n_repos += 1

    if n_commits:
        indexer.update_commit_stats()
        indexer.close()

    if args.upload:
        suffix = re.sub(r"[^0-9.]", "", timestamp())
        upload_file(args.db, f"git-indexer-{suffix}.db")

    log(f"finished indexing {n_commits} commits in {n_repos} repositories")


def parse_args(args: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        default=False,
        help="Overwrite existing repo directory",
    )
    parser.add_argument(
        "--index",
        action="store_true",
        default=False,
        help="Index repositories",
    )
    parser.add_argument(
        "--mirror",
        action="store_true",
        default=False,
        help="Mirror repositories",
    )

    parser.add_argument(
        "--filter",
        dest="filter",
        required=False,
        default="*",
        help="Match repository patterns",
    )
    parser.add_argument(
        "--query",
        dest="query",
        required=False,
        default="",
        help="Query for Github or Gitlab. For local repos, the base path",
    )
    parser.add_argument(
        "--source",
        dest="source",
        required=False,
        help="source of repositories, e.g. local, github, gitlab",
    )
    parser.add_argument(
        "--db",
        dest="db",
        required=False,
        default=os.path.expanduser("db/git-indexer.db"),
        help="local data for storing indexed data",
    )
    parser.add_argument(
        "--output",
        dest="output",
        required=False,
        help="Specify base output directory",
    )
    parser.add_argument(
        "--upload",
        action="store_true",
        default=False,
        help="Uplaod database file to Google Cloud Storage",
    )

    ns = parser.parse_args(args)

    if ns.mirror and ns.index:
        parser.error("both --index or --mirror are specified, can only choose one")

    if not ns.mirror and not ns.index:
        parser.error("either --index or --mirror must be specified")

    if ns.index and ns.db is None:
        parser.error("--db must be set")

    if not ns.source:
        parser.error("--source is required")

    if ns.mirror and ns.output is None:
        parser.error("--output must be specified when --mirror is used")

    if ns.mirror and ns.source == "local":
        parser.error("--source must be github or gitlab when --mirror is used")

    if ns.source == "local":
        ns.query = os.path.abspath(os.path.expanduser(ns.query))

    if ns.output is not None:
        ns.output = os.path.abspath(os.path.expanduser(ns.output))

    # print(ns)
    return ns


if __name__ == "__main__":
    args = parse_args(sys.argv[1:])
    if args.mirror:
        run_mirror(args)
    elif args.index:
        run_indexer(args)
    else:
        # shouldn't happen
        pass
