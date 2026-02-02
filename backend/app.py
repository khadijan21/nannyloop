# backend/app.py
import os
from functools import wraps
from datetime import datetime, timedelta, timezone

from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import LoginManager, login_user, logout_user, login_required, current_user

from backend.models import db, User, Household, Child, LogEntry, InviteCode, ScheduleItem   




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
    return db.session.get(User, int(user_id))   


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

    

    when_raw = request.form.get("when", "").strip()
    ts = None
    if when_raw:
        # datetime-local comes as "YYYY-MM-DDTHH:MM"
        ts = datetime.strptime(when_raw, "%Y-%m-%dT%H:%M")

    log = LogEntry(
        household_id=current_user.household_id,
        child_id=child_id,
        carer_name=carer_name,
        category=category,
        notes=notes,
        timestamp=ts if ts else datetime.utcnow()
    )

    db.session.add(log)
    db.session.commit()

    return redirect(url_for("dashboard"))

@app.route("/add_event", methods=["POST"])
@login_required
def add_event():
    child_id = request.form.get("child_id", type=int)
    week = request.form.get("week", "").strip()

    title = request.form.get("title", "").strip()
    category = request.form.get("category", "Other").strip()
    notes = request.form.get("notes", "").strip()
    when_raw = request.form.get("start_time", "").strip()

    if not child_id or not title or not when_raw:
        flash("Please fill in title and time.", "error")
        return redirect(url_for("timetable", child_id=child_id, week=week) if child_id else url_for("timetable"))

    child = Child.query.filter_by(id=child_id, household_id=current_user.household_id).first()
    if not child:
        flash("Invalid child selected.", "error")
        return redirect(url_for("timetable"))

    try:
        # datetime-local gives "YYYY-MM-DDTHH:MM"
        start_time = datetime.strptime(when_raw, "%Y-%m-%dT%H:%M")
    except ValueError:
        flash("Invalid date/time format.", "error")
        return redirect(url_for("timetable", child_id=child_id, week=week))

    item = ScheduleItem(
        household_id=current_user.household_id,
        child_id=child_id,
        title=title,
        category=category,
        notes=notes if notes else None,
        start_time=start_time,
        created_by_user_id=current_user.id,
    )

    db.session.add(item)
    db.session.commit()

    flash("Timetable event added.", "success")
    return redirect(url_for("timetable", child_id=child_id, week=week))


@app.route("/timetable")
@login_required
def timetable():
    children = Child.query.filter_by(household_id=current_user.household_id).all()
    if not children:
        flash("Add a child first, then you can view the timetable.", "error")
        return redirect(url_for("dashboard"))

    selected_child_id = request.args.get("child_id", type=int)
    if selected_child_id is None:
        selected_child_id = children[0].id

    selected_child = Child.query.filter_by(
        id=selected_child_id,
        household_id=current_user.household_id
    ).first()

    if not selected_child:
        flash("Invalid child selected.", "error")
        return redirect(url_for("dashboard"))

    week_str = request.args.get("week")
    if week_str:
        start_of_week = datetime.strptime(week_str, "%Y-%m-%d")
    else:
        today = datetime.utcnow()
        start_of_week = today - timedelta(days=today.weekday())

    start_of_week = start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_week = start_of_week + timedelta(days=7)

    prev_week = start_of_week - timedelta(days=7)
    next_week = start_of_week + timedelta(days=7)

    hours = list(range(6, 22, 2))  # 06:00 to 20:00 in 2 hour slots

    # logs
    logs = (
        LogEntry.query
        .filter_by(household_id=current_user.household_id, child_id=selected_child.id)
        .filter(LogEntry.timestamp >= start_of_week, LogEntry.timestamp < end_of_week)
        .order_by(LogEntry.timestamp.asc())
        .all()
    )

    # timetable events
    events = (
        ScheduleItem.query
        .filter_by(household_id=current_user.household_id, child_id=selected_child.id)
        .filter(ScheduleItem.start_time >= start_of_week, ScheduleItem.start_time < end_of_week)
        .order_by(ScheduleItem.start_time.asc())
        .all()
    )

    # grid: (day_index, hour_slot) -> list of entries
    grid = {}

    def slot_for(dt):
        hour_slot = (dt.hour // 2) * 2
        if hour_slot < 6:
            hour_slot = 6
        if hour_slot > 20:
            hour_slot = 20
        return hour_slot

    for ev in events:
        dt = ev.start_time
        day_index = (dt.date() - start_of_week.date()).days
        if 0 <= day_index <= 6:
            grid.setdefault((day_index, slot_for(dt)), []).append({
                "kind": "event",
                "category": ev.category,
                "time": dt,
                "title": ev.title,
                "notes": ev.notes or "",
            })

    for lg in logs:
        dt = lg.timestamp
        day_index = (dt.date() - start_of_week.date()).days
        if 0 <= day_index <= 6:
            grid.setdefault((day_index, slot_for(dt)), []).append({
                "kind": "log",
                "category": lg.category,
                "time": dt,
                "title": lg.category,
                "notes": lg.notes,
                "carer": lg.carer_name,
            })

    # sort each cell by time
    for key in grid:
        grid[key].sort(key=lambda x: x["time"])

    return render_template(
        "timetable.html",
        children=children,
        selected_child_id=selected_child.id,
        start_of_week=start_of_week,
        end_of_week=end_of_week,
        prev_week=prev_week,
        next_week=next_week,
        hours=hours,
        grid=grid,
        timedelta=timedelta
    )

