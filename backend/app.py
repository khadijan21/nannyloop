# backend/app.py
import os
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import LoginManager, login_user, logout_user, login_required, current_user

from backend.models import db, User, Household, Child, LogEntry, InviteCode


app = Flask(__name__)

app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-me")
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///nannyloop.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)

login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.init_app(app)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


def role_required(role_name: str):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for("login"))
            if current_user.role != role_name:
                flash("You do not have permission to access that.", "error")
                return redirect(url_for("dashboard"))
            return fn(*args, **kwargs)
        return wrapper
    return decorator


@app.route("/")
def home():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    children = Child.query.filter_by(household_id=current_user.household_id).all()
    logs = (
        LogEntry.query
        .filter_by(household_id=current_user.household_id)
        .order_by(LogEntry.timestamp.desc())
        .all()
    )

    active_invites = []
    if current_user.role == "parent":
        active_invites = (
            InviteCode.query
            .filter_by(household_id=current_user.household_id)
            .order_by(InviteCode.created_at.desc())
            .limit(5)
            .all()
        )

    return render_template(
        "index.html",
        children=children,
        logs=logs,
        active_invites=active_invites
    )


@app.route("/register-parent", methods=["GET", "POST"])
def register_parent():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        password = request.form["password"]
        household_name = request.form.get("household_name", "").strip()

        if User.query.filter_by(email=email).first():
            flash("That email is already registered.", "error")
            return redirect(url_for("register_parent"))

        household = Household(name=household_name or "My Household")
        db.session.add(household)
        db.session.commit()

        user = User(email=email, role="parent", household_id=household.id)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        login_user(user)
        return redirect(url_for("dashboard"))

    return render_template("register_parent.html")


@app.route("/register-carer", methods=["GET", "POST"])
def register_carer():
    if request.method == "POST":
        invite_code = request.form["invite_code"].strip()
        email = request.form["email"].strip().lower()
        password = request.form["password"]

        invite = InviteCode.query.filter_by(code=invite_code).first()
        if not invite or not invite.is_valid():
            flash("Invite code is invalid or expired.", "error")
            return redirect(url_for("register_carer"))

        if User.query.filter_by(email=email).first():
            flash("That email is already registered.", "error")
            return redirect(url_for("register_carer"))

        user = User(email=email, role="carer", household_id=invite.household_id)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        invite.used_by_user_id = user.id
        invite.used_at = db.func.now()
        db.session.commit()

        login_user(user)
        return redirect(url_for("dashboard"))

    return render_template("register_carer.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        password = request.form["password"]

        user = User.query.filter_by(email=email).first()
        if not user or not user.check_password(password):
            flash("Invalid email or password.", "error")
            return redirect(url_for("login"))

        login_user(user)
        return redirect(url_for("dashboard"))

    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


@app.route("/create_invite", methods=["POST"])
@login_required
@role_required("parent")
def create_invite():
    hours_raw = request.form.get("hours", "").strip()
    hours = int(hours_raw) if hours_raw.isdigit() else None

    invite = InviteCode.create(
        household_id=current_user.household_id,
        created_by_user_id=current_user.id,
        hours=hours
    )
    db.session.add(invite)
    db.session.commit()

    flash("Invite created.", "success")
    return redirect(url_for("dashboard"))


@app.route("/add_child", methods=["POST"])
@login_required
def add_child():
    name = request.form["name"].strip()
    dob = request.form["dob"].strip()

    child = Child(
        household_id=current_user.household_id,
        name=name,
        date_of_birth=dob
    )
    db.session.add(child)
    db.session.commit()

    return redirect(url_for("dashboard"))


@app.route("/add_log", methods=["POST"])
@login_required
def add_log():
    child_id = int(request.form["child_id"])
    carer_name = request.form["carer"].strip()
    category = request.form["category"].strip()
    notes = request.form["notes"].strip()

    child = Child.query.filter_by(id=child_id, household_id=current_user.household_id).first()
    if not child:
        flash("Invalid child selected.", "error")
        return redirect(url_for("dashboard"))

    log = LogEntry(
        household_id=current_user.household_id,
        child_id=child_id,
        carer_name=carer_name,
        category=category,
        notes=notes
    )
    db.session.add(log)
    db.session.commit()

    return redirect(url_for("dashboard"))


if __name__ == "__main__":
    with app.app_context():
        db.create_all()

    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
