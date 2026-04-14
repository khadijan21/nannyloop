# backend/app.py

import os
from functools import wraps
from datetime import datetime, timedelta, timezone
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from backend.models import db, User, Household, Child, LogEntry, InviteCode, ScheduleItem, ScheduleException, AISummary 
app = Flask(__name__, instance_relative_config=True)
os.makedirs(app.instance_path, exist_ok=True)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-me")
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(app.instance_path, "nannyloop.db")
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
    summaries = (
        AISummary.query
        .filter_by(household_id=current_user.household_id)
        .order_by(AISummary.created_at.desc())
        .all()
    )
    return render_template(
        "index.html",
        children=children,
        logs=logs,
        active_invites=active_invites,
        summaries=summaries
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



def build_weekly_summary(child_name, logs):
    total_logs = len(logs)

    if total_logs == 0:
        return f"No logs were recorded for {child_name} this week."

    category_counts = {}
    all_notes = []

    for log in logs:
        category_counts[log.category] = category_counts.get(log.category, 0) + 1
        if log.notes:
            all_notes.append(log.notes.lower())

    notes_text = " ".join(all_notes)

    sleep_count = category_counts.get("Sleep", 0)
    diet_count = category_counts.get("Diet", 0)
    behaviour_count = category_counts.get("Behaviour", 0)
    medical_count = category_counts.get("Medical", 0)
    other_count = category_counts.get("Other", 0)

    sorted_categories = sorted(category_counts.items(), key=lambda x: x[1], reverse=True)
    top_categories = [name.lower() for name, count in sorted_categories[:2]]

    summary_parts = [f"{child_name.capitalize()} had {total_logs} log entries this week."]

    if len(top_categories) == 1:
        summary_parts.append(f"Most updates were related to {top_categories[0]}.")
    elif len(top_categories) >= 2:
        summary_parts.append(f"Most updates were related to {top_categories[0]} and {top_categories[1]}.")

    detail_parts = []

    if sleep_count:
        detail_parts.append(f"{sleep_count} about sleep")
    if diet_count:
        detail_parts.append(f"{diet_count} about diet")
    if behaviour_count:
        detail_parts.append(f"{behaviour_count} about behaviour")
    if medical_count:
        detail_parts.append(f"{medical_count} about medical concerns")
    if other_count:
        detail_parts.append(f"{other_count} in other categories")

    if detail_parts:
        if len(detail_parts) == 1:
            summary_parts.append(f"There was {detail_parts[0]}.")
        else:
            summary_parts.append("This included " + ", ".join(detail_parts[:-1]) + f", and {detail_parts[-1]}.")

    concern_phrases = []

    behaviour_keywords = {
        "meltdown": "meltdowns",
        "tantrum": "tantrums",
        "cry": "crying",
        "cried": "crying",
        "fit": "distressed behaviour",
        "erratic": "erratic behaviour",
        "aggressive": "aggressive behaviour",
        "upset": "being upset",
    }

    sleep_keywords = {
        "tired": "tiredness",
        "sleepy": "sleepiness",
        "slept": "sleep changes",
        "nap": "naps",
        "woke": "waking issues",
        "wake": "waking issues",
    }

    diet_keywords = {
        "refused": "food refusal",
        "appetite": "appetite changes",
        "ate": "eating patterns",
        "hungry": "hunger",
        "drank": "drinking patterns",
        "food": "food-related issues",
    }

    medical_keywords = {
        "fever": "fever",
        "vomit": "vomiting",
        "vomited": "vomiting",
        "blood pressure": "blood pressure concerns",
        "rash": "a rash",
        "temperature": "temperature concerns",
        "pain": "pain",
        "medicine": "medication",
    }

    def collect_matches(keyword_map):
        found = []
        for keyword, label in keyword_map.items():
            if keyword in notes_text and label not in found:
                found.append(label)
        return found

    behaviour_found = collect_matches(behaviour_keywords)
    sleep_found = collect_matches(sleep_keywords)
    diet_found = collect_matches(diet_keywords)
    medical_found = collect_matches(medical_keywords)

    if behaviour_found:
        concern_phrases.append("Behaviour notes mentioned " + ", ".join(behaviour_found[:2]) + ".")
    if sleep_found:
        concern_phrases.append("Sleep-related notes mentioned " + ", ".join(sleep_found[:2]) + ".")
    if diet_found:
        concern_phrases.append("Diet-related notes mentioned " + ", ".join(diet_found[:2]) + ".")
    if medical_found:
        concern_phrases.append("Medical notes mentioned " + ", ".join(medical_found[:2]) + ".")

    if concern_phrases:
        summary_parts.extend(concern_phrases)

    if medical_count == 0:
        summary_parts.append("No medical concerns were recorded this week.")

    if behaviour_count >= 2:
        summary_parts.append("There were repeated behaviour-related updates this week.")

    summary_parts.append("This summary highlights key patterns based on recorded logs and notes.")

    return " ".join(summary_parts)


@app.route("/add_child", methods=["POST"])
@login_required
@role_required("parent")
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

@app.route("/generate_summary", methods=["POST"])
@login_required
def generate_summary():
    child_id = request.form.get("child_id", type=int)

    child = Child.query.filter_by(
        id=child_id,
        household_id=current_user.household_id
    ).first()

    if not child:
        flash("Invalid child selected.", "error")
        return redirect(url_for("dashboard"))

    today = datetime.utcnow()
    start_of_week = today - timedelta(days=today.weekday())
    start_of_week = start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_week = start_of_week + timedelta(days=7)

    logs = (
        LogEntry.query
        .filter_by(household_id=current_user.household_id, child_id=child.id)
        .filter(LogEntry.timestamp >= start_of_week, LogEntry.timestamp < end_of_week)
        .order_by(LogEntry.timestamp.asc())
        .all()
    )

    summary_text = build_weekly_summary(child.name, logs)

    existing_summary = (
        AISummary.query
        .filter_by(
            household_id=current_user.household_id,
            child_id=child.id,
            week_start=start_of_week
        )
        .first()
    )

    if existing_summary:
        existing_summary.summary_text = summary_text
    else:
        new_summary = AISummary(
            household_id=current_user.household_id,
            child_id=child.id,
            summary_text=summary_text,
            week_start=start_of_week
        )
        db.session.add(new_summary)

    db.session.commit()

    flash("Weekly summary generated.", "success")
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
    repeat_type = request.form.get("repeat_type", "").strip()
    repeat_until_raw = request.form.get("repeat_until", "").strip()

    if not child_id or not title or not when_raw:
        flash("Please fill in title and time.", "error")
        return redirect(url_for("timetable", child_id=child_id, week=week) if child_id else url_for("timetable"))

    child = Child.query.filter_by(id=child_id, household_id=current_user.household_id).first()
    if not child:
        flash("Invalid child selected.", "error")
        return redirect(url_for("timetable"))

    try:
        start_time = datetime.strptime(when_raw, "%Y-%m-%dT%H:%M")
    except ValueError:
        flash("Invalid date/time format.", "error")
        return redirect(url_for("timetable", child_id=child_id, week=week))

    repeat_until = None
    rrule = None

    if repeat_type:
        if repeat_type == "daily":
            rrule = "FREQ=DAILY"
        elif repeat_type == "weekly":
            rrule = "FREQ=WEEKLY"
        else:
            flash("Invalid repeat option.", "error")
            return redirect(url_for("timetable", child_id=child_id, week=week))

        if repeat_until_raw:
            try:
                repeat_until_date = datetime.strptime(repeat_until_raw, "%Y-%m-%d")
                repeat_until = repeat_until_date.replace(hour=23, minute=59, second=59)
            except ValueError:
                flash("Invalid repeat until date.", "error")
                return redirect(url_for("timetable", child_id=child_id, week=week))

            if repeat_until < start_time:
                flash("Repeat until date must be after the start time.", "error")
                return redirect(url_for("timetable", child_id=child_id, week=week))

    item = ScheduleItem(
        household_id=current_user.household_id,
        child_id=child_id,
        title=title,
        category=category,
        notes=notes if notes else None,
        start_time=start_time,
        rrule=rrule,
        repeat_until=repeat_until,
        created_by_user_id=current_user.id,
    )

    db.session.add(item)
    db.session.commit()

    flash("Timetable event added.", "success")
    return redirect(url_for("timetable", child_id=child_id, week=week))
@app.route("/delete_event/<int:event_id>", methods=["POST"])
@login_required
def delete_event(event_id):
    week = request.form.get("week", "").strip()

    event = ScheduleItem.query.filter_by(
        id=event_id,
        household_id=current_user.household_id,
        is_deleted=False
    ).first()

    if not event:
        flash("Event not found.", "error")
        return redirect(url_for("timetable"))

    child_id = event.child_id
    event.is_deleted = True
    db.session.commit()

    flash("Event deleted.", "success")
    return redirect(url_for("timetable", child_id=child_id, week=week))

@app.route("/delete_event_occurrence/<int:event_id>", methods=["POST"])
@login_required
def delete_event_occurrence(event_id):
    week = request.form.get("week", "").strip()
    occurrence_date_raw = request.form.get("occurrence_date", "").strip()

    event = ScheduleItem.query.filter_by(
        id=event_id,
        household_id=current_user.household_id,
        is_deleted=False
    ).first()

    if not event:
        flash("Event not found.", "error")
        return redirect(url_for("timetable"))

    if not event.rrule:
        flash("This is not a recurring event.", "error")
        return redirect(url_for("timetable", child_id=event.child_id, week=week))

    try:
        occurrence_date = datetime.strptime(occurrence_date_raw, "%Y-%m-%d").date()
    except ValueError:
        flash("Invalid occurrence date.", "error")
        return redirect(url_for("timetable", child_id=event.child_id, week=week))

    already_skipped = ScheduleException.query.filter_by(
        schedule_item_id=event.id,
        skipped_date=occurrence_date
    ).first()

    if not already_skipped:
        ex = ScheduleException(
            schedule_item_id=event.id,
            skipped_date=occurrence_date
        )
        db.session.add(ex)
        db.session.commit()

    flash("Only this occurrence was deleted.", "success")
    return redirect(url_for("timetable", child_id=event.child_id, week=week))

@app.route("/delete_event_permanently/<int:event_id>", methods=["POST"])
@login_required
def delete_event_permanently(event_id):
    week = request.form.get("week", "").strip()

    event = ScheduleItem.query.filter_by(
        id=event_id,
        household_id=current_user.household_id,
        is_deleted=True
    ).first()

    if not event:
        flash("Event not found.", "error")
        return redirect(url_for("timetable"))

    child_id = event.child_id

    db.session.delete(event)
    db.session.commit()

    flash("Event permanently deleted.", "success")
    return redirect(url_for("timetable", child_id=child_id, week=week))

@app.route("/undo_delete_event/<int:event_id>", methods=["POST"])
@login_required
def undo_delete_event(event_id):
    week = request.form.get("week", "").strip()

    event = ScheduleItem.query.filter_by(
        id=event_id,
        household_id=current_user.household_id,
        is_deleted=True
    ).first()

    if not event:
        flash("Deleted event not found.", "error")
        return redirect(url_for("timetable"))

    child_id = event.child_id
    event.is_deleted = False
    db.session.commit()

    flash("Event restored.", "success")
    return redirect(url_for("timetable", child_id=child_id, week=week))

@app.route("/edit_event/<int:event_id>", methods=["GET"])
@login_required
def edit_event(event_id):
    week = request.args.get("week", "").strip()

    event = ScheduleItem.query.filter_by(
        id=event_id,
        household_id=current_user.household_id,
        is_deleted=False
    ).first()

    if not event:
        flash("Event not found.", "error")
        return redirect(url_for("timetable"))

    return render_template("edit_event.html", event=event, week=week)


@app.route("/update_event/<int:event_id>", methods=["POST"])
@login_required
def update_event(event_id):
    week = request.form.get("week", "").strip()

    event = ScheduleItem.query.filter_by(
        id=event_id,
        household_id=current_user.household_id,
        is_deleted=False
    ).first()

    if not event:
        flash("Event not found.", "error")
        return redirect(url_for("timetable"))

    title = request.form.get("title", "").strip()
    category = request.form.get("category", "Other").strip()
    notes = request.form.get("notes", "").strip()
    when_raw = request.form.get("start_time", "").strip()

    if not title or not when_raw:
        flash("Title and time are required.", "error")
        return redirect(url_for("edit_event", event_id=event.id, week=week))

    try:
        start_time = datetime.strptime(when_raw, "%Y-%m-%dT%H:%M")
    except ValueError:
        flash("Invalid date/time format.", "error")
        return redirect(url_for("edit_event", event_id=event.id, week=week))

    event.title = title
    event.category = category
    event.notes = notes if notes else None
    event.start_time = start_time

    db.session.commit()

    flash("Event updated.", "success")
    return redirect(url_for("timetable", child_id=event.child_id, week=week))



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
        .filter_by(
            household_id=current_user.household_id,
            child_id=selected_child.id,
            is_deleted=False
        )
        .order_by(ScheduleItem.start_time.asc())
        .all()
    )

    deleted_events = (
        ScheduleItem.query
        .filter_by(
            household_id=current_user.household_id,
            child_id=selected_child.id,
            is_deleted=True
        )
        .order_by(ScheduleItem.start_time.desc())
        .limit(5)
        .all()
    )

    exceptions = ScheduleException.query.all()
    skipped_lookup = {(ex.schedule_item_id, ex.skipped_date) for ex in exceptions}


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
        event_times = []

        if not ev.rrule:
            if start_of_week <= ev.start_time < end_of_week:
                event_times.append(ev.start_time)

        

        elif ev.rrule == "FREQ=DAILY":
            current_dt = ev.start_time

            while current_dt < start_of_week:
                current_dt += timedelta(days=1)

            while current_dt < end_of_week:
                if ev.repeat_until is None or current_dt <= ev.repeat_until:
                    if (ev.id, current_dt.date()) not in skipped_lookup:
                        event_times.append(current_dt)
                current_dt += timedelta(days=1)

        elif ev.rrule == "FREQ=WEEKLY":
            current_dt = ev.start_time

            while current_dt < start_of_week:
                current_dt += timedelta(days=7)

            while current_dt < end_of_week:
                if ev.repeat_until is None or current_dt <= ev.repeat_until:
                    if (ev.id, current_dt.date()) not in skipped_lookup:
                        event_times.append(current_dt)
                current_dt += timedelta(days=7)

        for dt in event_times:
            day_index = (dt.date() - start_of_week.date()).days
            if 0 <= day_index <= 6:
                grid.setdefault((day_index, slot_for(dt)), []).append({
                    "id": ev.id,
                    "kind": "event",
                    "category": ev.category,
                    "time": dt,
                    "title": ev.title,
                    "notes": ev.notes or "",
                    "rrule": ev.rrule,
                    "occurrence_date": dt.strftime("%Y-%m-%d"),
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
        timedelta=timedelta,
        deleted_events=deleted_events,

    )
@app.cli.command("init-db")
def init_db():
    """Create all database tables."""
    with app.app_context():
        db.create_all()
    print("Database tables created.")
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="127.0.0.1", port=port, debug=True)
