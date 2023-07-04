import fnmatch
import os
import re
import socket
import sys
import warnings
from datetime import datetime
from typing import Iterator, Optional
from urllib.parse import urlparse

import gitlab
import psutil
from git import InvalidGitRepositoryError
from github import Auth, BadCredentialsException, Github
from pydriller.git import Git

# files matches any of the regex will not be counted
# towards commit stats
IGNORE_PATTERNS = [
    re.compile(
        "^(vendor|Pods|target|YoutuOCWrapper|vos-app-protection|vos-processor|\\.idea|\\.vscode)/."  # noqa: E501
    ),
    re.compile("^[a-zA-Z0-9_]*?/Pods/"),
    re.compile("^.*(xcodeproj|xcworkspace)/."),
    re.compile(r".*\.(jar|pbxproj|lock|bk|bak|backup|class|swp|sum|pdf|png)$"),
    re.compile(r"^.*/?package-lock\.json$"),
    re.compile(r"^.*/?(\.next|node_modules|\.devcontainer)(/|$).*"),
]


def timestamp() -> str:
    return datetime.now().isoformat()[:19]


def rss() -> int:
    """return rss memory usage in MB"""
    return int(meminfo().rss / 1024 / 1024)


def meminfo():
    pid = os.getpid()
    proc = psutil.Process(pid)
    return proc.memory_info()


def is_git_repo(path: str) -> bool:
    try:
        repo = Git(path)
        repo.get_head()
        return True
    except InvalidGitRepositoryError:
        return False


def match_any(path: str, patterns: str) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in patterns.split(","))


def clone_to_browse_url(clone_url: str) -> str:
    """convert ssh based clone url to https based url"""
    url = urlparse(clone_url)
    http_url = ""
    if url.scheme in ["http", "https"]:
        http_url = clone_url
    elif url.scheme in ["ssh", "ssh+git"] or (url.scheme == "" and url.path.startswith("git@")):
        host, path = re.sub(r"^git@", "", url.path).split(":")
        # if you put a hack in one place, you'll have to put a hack in all places :(((
        if host == "gitlab-sbc":
            host = "gitlab.com"
        http_url = f"https://{host}/{path}"
    return re.sub(r"\.git$", "", http_url)


def should_exclude_from_stats(path: str) -> bool:
    """
    return true if the path should be ignore
    for calculating commit stats
    """
    for regex in IGNORE_PATTERNS:
        if regex.match(path):
            return True
    return False


def enumerate_local_repos(base_dir: str) -> Iterator[str]:
    for root, dirs, _ in os.walk(os.path.expanduser(base_dir), topdown=True):
        if ".git" in dirs:
            dirs.remove(".git")

        for dd in dirs:
            abs_path = os.path.abspath(root + "/" + dd)
            if is_git_repo(abs_path):
                yield abs_path


def enumerate_gitlab_repos(
    query: str, private_token: Optional[str] = None, url: str = "https://gitlab.com"
) -> Iterator[str]:
    if private_token is None:
        private_token = os.environ.get("GITLAB_TOKEN")
        if not private_token:
            print("GITLAB_TOKEN environment variable not set")
            sys.exit(1)

    gl = gitlab.Gitlab(url, private_token=private_token, per_page=100)
    for project in gl.search(scope="projects", search=query, get_all=True):
        clone_url = project["ssh_url_to_repo"]
        # unfortunate ssh_config on this machine
        if socket.gethostname() == "uno.local":
            clone_url = clone_url.replace("gitlab.com", "gitlab-sbc")
        yield clone_url


def enumerate_github_repos(query: str, access_token: Optional[str] = None, useHttpUrl: bool = False) -> Iterator[str]:
    if access_token is None:
        access_token = os.environ.get("GITHUB_TOKEN")

    try:
        gh = Github(auth=Auth.Token(access_token)) if access_token else Github()
        for rep in gh.search_repositories(query=query):
            yield rep.ssh_url
    except BadCredentialsException as e:
        print(f"authentication error => {e}")
    except Exception as e:
        print(f"gitlab search {query} error {type(e)} => {e}")


def log(msg: str) -> None:
    print(f"{timestamp()}:RSS {rss():4,} MB :{msg}")


def __shorten__(path: str, max_lenght: int) -> str:
    if len(path) > max_lenght:
        return path[:3] + "..." + path[(max_lenght - 6) * -1 :]
    else:
        return path


def display_url(clone_url: str, max_length: int = 64) -> str:
    url = re.sub(r"https?://[^\/]+", "", clone_url)  # remove http(s)://host portion of the url
    url = re.sub(r"git@.*:", "", url)  # remove the git@host: portion of the url
    url = __shorten__(url, max_length)
    return re.sub(r".git$", "", url)


def upload_file(source_file: str, destination: str) -> bool:
    with warnings.catch_warnings():
        # google cloud uses deprecated apis
        # suppress the warning locally
        warnings.simplefilter("ignore")
        from google.cloud import storage  # type: ignore [attr-defined] # noqa: E402

    # env variable GOOGLE_APPLICATION_CREDENTIALS must be point to
    # a service account json file
    if os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") is None:
        return False

    bucket_name = os.environ.get("GS_BUCKET_NAME", "vinolab")
    try:
        storage_client = storage.Client()
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(destination)
        blob.upload_from_filename(source_file)

        stats = os.stat(source_file)
        log(f"uploaded {source_file} to gs://{bucket_name}/{destination}, size {int(stats.st_size/1048576)} MB")
        return True
    except Exception as e:
        print(f"Failed to upload {source_file} to gs://{bucket_name}/{destination}: {e}")
        return False