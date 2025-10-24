import os
from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash
from pymongo import MongoClient
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash
from chatbot import get_chat_response
from bson.objectid import ObjectId

#  Load environment variables
load_dotenv(dotenv_path="config/.env")

#  Initialize Flask app
app = Flask(__name__)
app.secret_key = os.urandom(24)

#  MongoDB setup
MONGO_URI = os.getenv("MONGO_URI")
client = MongoClient(MONGO_URI)
db = client["EVO_AI_DB"]
users = db["users"]
chat_history = db["chat_history"]

#  Home route
@app.route("/")
def home():
    if "user_id" in session:
        return redirect(url_for("chatbot"))
    return render_template("index.html")

#  Login route
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        password = request.form["password"]
        user = users.find_one({"email": email})
        if user and check_password_hash(user["password"], password):
            session["user_id"] = str(user["_id"])
            flash("Login successful", "success")
            return redirect(url_for("chatbot"))
        flash("Invalid email or password.", "danger")
    return render_template("login.html")

#  Register route
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        password = request.form["password"]
        existing_user = users.find_one({"email": email})
        if existing_user:
            flash("Email already registered. Please log in.", "warning")
            return redirect(url_for("login"))
        hashed_password = generate_password_hash(password)
        new_user = users.insert_one({"email": email, "password": hashed_password})
        session["user_id"] = str(new_user.inserted_id)
        flash("Registration successful!", "success")
        return redirect(url_for("chatbot"))
    return render_template("register.html")

#  Chatbot route
@app.route("/chatbot")
def chatbot():
    if "user_id" not in session:
        flash("Please log in to access the chatbot.", "warning")
        return redirect(url_for("login"))
    return render_template("chat.html")

# Chat response route
@app.route("/get_response", methods=["POST"])
def get_response():
    user_input = request.json.get("message", "").strip()
    user_id = session.get("user_id", "guest")
    if not user_input:
        return jsonify({"response": "❌ Empty input received."})
    response = get_chat_response(user_input, user_id)
    chat_history.insert_one({
        "user_id": user_id,
        "user_input": user_input,
        "bot_response": response
    })
    return jsonify({"response": response})

# Logout route
@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("login"))

#  Run app
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

