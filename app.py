from flask import Flask, render_template

app = Flask(__name__)


@app.route("/")
def home():
    return render_template("home.html")


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/submit")
def submit_info():
    return render_template("submit.html")

@app.route("/events")
def events():
    return render_template("events.html")


@app.route("/dancers")
def dancers():
    return render_template("dancers.html")


@app.route("/battles")
def battles():
    return render_template("battles.html")


@app.route("/awards")
def awards():
    return render_template("awards.html")


@app.route("/verify")
def verify_claims():
    return render_template("verify_claims.html")


@app.route("/ask")
def ask_archive():
    return render_template("ask_archive.html")

if __name__ == "__main__":
    app.run(debug=True)