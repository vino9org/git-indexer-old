import os
import shlex

import pytest

import run


def test_cmdline_options():
    ## valid options
    args = run.parse_args(shlex.split("--index --source gitlab --dry-run"))
    assert args.index and args.source == "gitlab" and args.dry_run

    args = run.parse_args(shlex.split("--mirror --source gitlab --output local_path/repos --overwrite"))
    assert args.mirror and args.source == "gitlab" and args.output and args.overwrite and not args.dry_run

    ## invalid options
    # --mirror and --index are mutually exclusive
    with pytest.raises(SystemExit):
        run.parse_args(shlex.split("--index --mirror"))

    # neither --mirror nor --index is not valid
    with pytest.raises(SystemExit):
        run.parse_args(shlex.split("--output somepath/tmp"))

    # source must be specific when either --mirror or --index is used
    with pytest.raises(SystemExit):
        run.parse_args(shlex.split("--mirror --dry-run"))

    # source cannot be local when --mirror is used
    with pytest.raises(SystemExit):
        run.parse_args(shlex.split("--mirror --source local"))

    # unrecognized option --database
    with pytest.raises(SystemExit):
        run.parse_args(shlex.split("--index --source gitlab --database test.db --dry-run"))


@pytest.mark.skipif(os.environ.get("GITHUB_TOKEN") is not None, reason="does not work in Github action, no ssh key")
def test_run_mirror(tmp_path, github_test_repo):
    args = run.parse_args(
        shlex.split(
            f"--mirror --query {github_test_repo} --source github --filter * --output {tmp_path.as_posix()}/ --overwrite"  # noqa E501
        )
    )
    # 1st run should trigger a git clone
    run.run_mirror(args)
    # 2nd run should trigger a fetch
    run.run_mirror(args)


@pytest.mark.skipif(os.environ.get("GITHUB_TOKEN") is not None, reason="does not work in Github action, no ssh key")
def test_run_indexer(tmp_path, github_test_repo):
    args = run.parse_args(
        shlex.split(f"--index --query {github_test_repo} --source github --filter * --db {tmp_path}/tmp.db")
    )
    run.run_indexer(args)


def test_enumberate_from_file(tmp_path):
    repo_lst = str(tmp_path / "repos.txt")
    with open(repo_lst, "w") as f:
        f.write("/user/repo1.git\n")
        f.write("#/user/repo2.git\n")

    repos = list(run.enumberate_from_file(repo_lst, ""))
    assert len(repos) == 1 and "repo1" in repos[0]
