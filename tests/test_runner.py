import shlex

import pytest
from constants import __TEST_GITHUB_REPO___

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


@pytest.mark.xfail(reason="fails with ssh key problem when running in Github action")
def test_run_mirror(tmp_path):
    args = run.parse_args(
        shlex.split(
            f"--mirror --query {__TEST_GITHUB_REPO___} --source github --filter * --output {tmp_path.as_posix()}/ --overwrite"  # noqa E501
        )
    )
    run.run_mirror(args)


@pytest.mark.xfail(reason="fails with ssh key problem when running in Github action")
def test_run_indexer():
    args = run.parse_args(
        shlex.split(f"--index --query {__TEST_GITHUB_REPO___} --source github --filter *")  # noqa E501
    )
    run.run_indexer(args)
