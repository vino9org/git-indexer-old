import os
import re
import warnings

from dotenv import load_dotenv
from flask import Flask, flash, redirect, render_template, request, url_for
from flask_sqlalchemy import SQLAlchemy
from werkzeug.middleware.proxy_fix import ProxyFix
from wtforms.fields import StringField, SubmitField

from indexer.models import Author, Commit, Repository

with warnings.catch_warnings():
    # these packages uses flask.Markup
    # suppress the warning when running tests
    warnings.simplefilter("ignore")
    from flask_bootstrap import Bootstrap5  # noqa: E402
    from flask_wtf import FlaskForm  # noqa: E402

__PAGE_SIZE__ = 50

load_dotenv()


def init_app() -> Flask:
    app = Flask(__name__, template_folder="../templates", static_folder="../static")
    secret_key = os.environ.get("SECRET_KEY")
    app.config["SECRET_KEY"] = secret_key if secret_key else os.urandom(32)

    if os.environ.get("KUBERNETES_SERVICE_HOST"):
        print("running in kubernetes, using proxy fix")
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)  # type: ignore

    return app


app = init_app()
bootstrap = Bootstrap5(app)


def init_db(app: Flask) -> SQLAlchemy:
    uri = os.environ.get("SQLALCHEMY_DATABASE_URI")
    sqlite_file = os.environ.get("SQLITE_FILE", "")
    if uri is None and sqlite_file == "":
        raise ValueError("please set either SQLALCHEMY_DATABASE_URI or SQLITE_FILE")
    elif uri is None:
        uri = f"sqlite:///{os.path.abspath(os.path.expanduser(sqlite_file))}"

    app.config["SQLALCHEMY_DATABASE_URI"] = uri
    print(f"connecting to {uri}")
    return SQLAlchemy(app)


db = init_db(app)


class SearchForm(FlaskForm):
    query = StringField(label="Enter a git commit hash, email address or repository name")
    search = SubmitField("Search")


@app.route("/")
def index():
    return redirect("/search")


@app.route("/search", methods=["GET"])
def search_page():
    return render_template("search.html", form=SearchForm())


@app.route("/search", methods=["POST"])
def search():
    search_term = request.form["query"].strip()
    commits = None
    title = "Single Commit"

    if len(search_term) == 40 and re.match(r"[0-9a-f]{40}", search_term):
        # looks like a git hash
        commits = db.session.query(Commit).filter(Commit.sha.__eq__(search_term)).all()

    elif "@" in search_term:
        # extract the email address from the search_term
        match = re.search(r"\b(\S+@\S+)\b", search_term)
        if match:
            search_email = match[0]
            authors = db.session.query(Author).filter(Author.real_email.__eq__(search_email)).all()
            if len(authors) > 0:
                title = f"Commits by {search_email}"
                commits = (
                    db.session.query(Commit)
                    .filter(Commit.author_id.in_([a.id for a in authors]))
                    .order_by(Commit.n_lines_changed.desc())
                    .limit(__PAGE_SIZE__)
                    .all()
                )
            else:
                flash(f"cannot find any author with the email {search_email}", "danger")
        else:
            flash("please enter a valid email address", "danger")

    else:
        # assume the serach term is a repository name
        repo = db.session.query(Repository).filter(Repository.repo_name.__eq__(search_term)).first()
        if repo:
            title = f"Commits in repository {repo.repo_name}"
            commits = (
                db.session.query(Commit)
                .filter(Commit.repos.any(id=repo.id))
                .order_by(Commit.n_lines_changed.desc())
                .limit(__PAGE_SIZE__)
            ).all()
        else:
            flash(f"cannot find any repo that matchs {search_term}", "danger")

    if commits and len(commits) > 0:
        return render_template("git_commit_list.html", commits=commits, title=title)
    else:
        return redirect(url_for("search_page"))
