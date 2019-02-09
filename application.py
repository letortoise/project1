import os
import requests

from flask import Flask, session, render_template, request, redirect, url_for, jsonify
from flask_session import Session
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker

app = Flask(__name__)

key = "OM7xyd7tYOXjMgEIZlKwLQ"

# Check for environment variable
if not os.getenv("DATABASE_URL"):
    raise RuntimeError("DATABASE_URL is not set")

# Configure session to use filesystem
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Set up database
engine = create_engine(os.getenv("DATABASE_URL"))
db = scoped_session(sessionmaker(bind=engine))


@app.route("/")
def index():
    # Redirect logged-in user to search page
    if 'user_id' in session:
        return redirect(url_for('search'))

    # Redirect user to login page when not logged in
    return redirect(url_for('login'))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")

    if request.method == "POST":
        #Get form info
        username = request.form.get("username")
        password = request.form.get("password")

        #Log the user in
        user_id = db.execute("SELECT id FROM users WHERE username = :username AND password = :password",
                {"username": username, "password": password}).fetchone()
        if user_id is None:
            return render_template("error.html", message="Incorrect username or password")
        session['user_id'] = user_id[0]

        #Redirect the user to '/'
        return redirect(url_for('index'))



@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("registration.html")
    if request.method == "POST":
        #Get form info
        username = request.form.get("username")
        password = request.form.get("password")

        #Make sure username isn't taken already
        if db.execute("SELECT * FROM users WHERE username = :username",
                {"username": username}).rowcount != 0:
            return render_template("error.html", message="Username is already taken")

        #Create the account
        db.execute("INSERT INTO users (username, password) VALUES (:username, :password)",
                {"username": username, "password": password})
        db.commit()
        return render_template("success.html", message="You've been registered!")


@app.route("/logout")
def logout():
    #Log the user out
    if 'user_id' in session:
        session.pop('user_id')

    #Redirect the user to the home page
    return redirect(url_for('index'))


@app.route("/search", methods=["GET", "POST"])
def search():
    """Search for a book and list the results."""

    if request.method == "GET":
        return render_template("search.html")

    # List the search results
    if request.method == "POST":

        # Determine search criterion
        try:
            search_by = request.args['search_by']
        except KeyError:
            return render_template("error.html", message="Must search by title, author, or ISBN.")

        # Search by ISBN, title, or author
        if search_by == "isbn":
            isbn = request.form.get("isbn")
            results = db.execute("SELECT * FROM books WHERE isbn = :isbn", {"isbn": isbn}).fetchall()
        elif search_by == "title":
            title = request.form.get("title")
            results = db.execute("SELECT * FROM books WHERE title LIKE :title ORDER BY title ASC",
                    {"title" : title+"%"}).fetchall()
        elif search_by == "author":
            author = request.form.get("author")
            results = db.execute("SELECT * FROM books WHERE author LIKE :author ORDER BY author ASC",
                    {"author" : author+"%"}).fetchall()
        else:
            return render_template("error.html", message="Something went wrong.")

        # Display the results
        if book is None:
            return render_template("error.html", message = "No such book")
        return render_template("results.html", results = results)


@app.route("/book/<int:book_id>")
def book(book_id):
    """Lists information and reviews about a single book."""

    # Make sure book exists
    book = db.execute("SELECT * FROM books WHERE id = :id", {"id": book_id}).fetchone()
    if book is None:
        return render_template("error.html")

    # Get reviews for the database
    reviews = db.execute("SELECT rating, review, username FROM reviews JOIN users\
            ON reviews.user_id = users.id WHERE book_id = :book_id",
            {"book_id":book_id}).fetchall()

    # Get Goodreads information on book
    res = requests.get("https://www.goodreads.com/book/review_counts.json",
            params={"key":key, "isbns": book.isbn})
    goodreads = res.json()['books'][0]

    # Display book information and reviews
    return render_template("book.html", book=book, reviews=reviews, goodreads=goodreads)

@app.route("/review/<int:book_id>", methods=["GET", "POST"])
def review(book_id):
    """Write a book reivew."""

    # Make sure user is logged in
    if 'user_id' not in session:
        return render_template("error.html", message="You must be logged in to leave a review.")

    # Don't let users leave multiple reviews
    user_id = session['user_id']
    if db.execute("SELECT * FROM reviews WHERE user_id = :user_id AND book_id = :book_id",
            {"user_id" : user_id, "book_id" : book_id}).fetchall():
        return render_template("error.html", message="You can only leave one review per book.")

    # Submit a review
    if request.method == "POST":
        # Get form info
        rating = request.form.get("rating")
        review = request.form.get("review")

        # Add the review to the database
        db.execute("INSERT INTO reviews (rating, review, book_id, user_id)\
                VALUES (:rating, :review, :book_id, :user_id)",
                {"rating":rating, "review":review, "book_id":book_id, "user_id":user_id})
        db.commit()

        # Redirect user to the book page
        return redirect(url_for('book', book_id = book_id))

    # Display the review form
    return render_template("review_form.html")

@app.route("/api/<string:isbn>")
def api(isbn):

    # Make sure book is in database
    book = db.execute("SELECT * FROM books WHERE isbn = :isbn", {"isbn": isbn}).fetchone()
    if book is None:
        return render_template("error.html", message="No such book")
    print(book)

    # Get review count and average score
    review_count = db.execute("SELECT COUNT(*) FROM reviews WHERE book_id = :book_id", {"book_id": book.id}).fetchone()[0]
    average_score = round(db.execute("SELECT AVG(rating) FROM reviews WHERE book_id = :book_id", {"book_id": book.id}).fetchone()[0], 1)

    print(type(average_score))

    # Format data for response
    data = {
        "title": book.title,
        "author": book.author,
        "year": book.year,
        "isbn": book.isbn,
        "review_count": review_count,
        "average_score": str(average_score)
    }

    return jsonify(data)
