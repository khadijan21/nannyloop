from flask import Flask, render_template
from .models import db  # relative import

app = Flask(__name__)

# SQLite database file will be created in the project root (same level as /backend)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///nannyloop.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)


@app.route("/")
def home():
    return render_template("index.html")


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)
