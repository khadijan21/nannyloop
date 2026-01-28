# backend/app.py
import os
from flask import Flask, render_template, request, redirect, url_for
from backend.models import db, Child, LogEntry


app = Flask(__name__)


# SQLite database (works locally; on Render free it won’t persist long-term)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///nannyloop.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False


db.init_app(app)


@app.route("/")
def home():
    children = Child.query.all()
    logs = LogEntry.query.order_by(LogEntry.timestamp.desc()).all()
    return render_template("index.html", children=children, logs=logs)


@app.route("/add_child", methods=["POST"])
def add_child():
    name = request.form["name"]
    dob = request.form["dob"]


    child = Child(name=name, date_of_birth=dob)
    db.session.add(child)
    db.session.commit()


    return redirect(url_for("home"))


@app.route("/add_log", methods=["POST"])
def add_log():
    child_id = request.form["child_id"]
    carer_name = request.form["carer"]
    category = request.form["category"]
    notes = request.form["notes"]


    log = LogEntry(
        child_id=child_id,
        carer_name=carer_name,
        category=category,
        notes=notes
    )
    db.session.add(log)
    db.session.commit()


    return redirect(url_for("home"))


if __name__ == "__main__":
    with app.app_context():
        db.create_all()


    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
