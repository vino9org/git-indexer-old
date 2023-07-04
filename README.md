# Utlity that scan git repositories and extract metrics

## Run

```shell

# setup local python venv using Poetry
poetry shell
poetry install

# setup local python venv using stanard tools
python -m venv venv
source venv/bin/activate
pip install requirements.txt


export GITLAB_TOKEN='glpat...'
export GITHUB_TOKEN='ghpat...'

# index repos hosted on github
python run.py --index --source github --query "sloppycoder/bank-demo" --db ~/git-indexer.db

# index repos hosted on gitlab that matches the query and filter
python run.py --index --source gitlab --query "vino9group" --filter "test*"

# index local repos under a directory
python run.py --index --source local --query "~/tmp/repos" --db local_repos.db

# mirrors the repos hosted on gitlab to a local directory
# overwrite local directory if they already exists
python run.py --mirror --source gitlab --query "vino9group" --filter "test*" --output "~/tmp/repos" --overwrite


# run the simple gui
flask --app gui run

```

This project is set up Python project with dev tooling pre-configured

* black
* flake8
* isort
* mypy
* VS Code support

## Develop the code for the stack

```shell

# run unit tests
export GITLAB_TOKEN=glat...

pytest -v

```

## prep database

create new user and database if neccessary

```text

CREATE USER git WITH PASSWORD 'git';
CREATE DATABASE gitindexer;
GRANT ALL PRIVILEGES ON DATABASE gitindexer TO git;
```
