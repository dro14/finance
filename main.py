import os

from cs50 import SQL
from flask import Flask, redirect, render_template, request, session
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd, now

# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""

    # Save user id
    userid = session["user_id"]

    # Get what stocks and how many of them user owns
    user_data = db.execute("SELECT symbol, shares FROM shares WHERE userid=?;", userid)

    # Construct a list of dictionaries for index.html
    records = []
    total_value = 0.0
    for _, elem in enumerate(user_data):
        symbol = elem["symbol"]
        quote = lookup(symbol)
        value = elem["shares"] * quote["price"]
        records.append({
            "name": quote["name"],
            "symbol": quote["symbol"],
            "price": usd(quote["price"]),
            "shares": elem["shares"],
            "value": usd(value)
        })
        total_value += value

    # Get how much cash user has
    cash = db.execute("SELECT cash FROM users WHERE id=?;", userid)[0]["cash"]

    # Calculate sum of cash and value of stocks user owns
    grand_total = cash + total_value

    return render_template("index.html", records=records, total_value=usd(total_value), cash=usd(cash), grand_total=usd(grand_total))


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""

    # User reached route via GET (as by clicking a link)
    if request.method == "GET":
        return render_template("buy.html")

    # User reached route via POST (as by submitting a form via POST)
    else:
        # Save user id
        userid = session["user_id"]

        # Check for symbol
        symbol = request.form.get("symbol")
        if not symbol:
            return apology("must specify symbol")

        # Look up for submitted symbol
        quote = lookup(symbol)

        # Check for valid symbol
        if not quote:
            return apology("invalid stock symbol")

        # Save data from API
        name = quote["name"]
        symbol = quote["symbol"]
        price = quote["price"]

        # Check for shares
        shares = request.form.get("shares")
        if not shares:
            return apology("must specify shares")

        # Check for valid type
        try:
            shares = int(shares)
        except ValueError:
            return apology("shares is of invalid data type")

        # Check for negative value
        if shares < 0:
            return apology("shares must be greater than zero")

        # Get cash user has
        cash = db.execute("SELECT cash FROM users WHERE id=?;", userid)[0]["cash"]

        # Check for enough cash
        if shares * price > cash:
            return apology("not enough cash")

        # Subtract value from cash and update record
        db.execute("UPDATE users SET cash=cash-?*? WHERE id=?;", shares, price, userid)

        # Get how many shares users own of this stock
        user_data = db.execute("SELECT shares FROM shares WHERE userid=? AND symbol=?;", userid, symbol)

        # Add record if user does not own any of this stock
        if len(user_data) == 0:
            db.execute("INSERT INTO shares (userid, name, symbol, shares) VALUES (?, ?, ?, ?);", userid, name, symbol, shares)
        # Update record if user already owns some of this stock
        else:
            db.execute("UPDATE shares SET shares=shares+? WHERE userid=? AND symbol=?;", shares, userid, symbol)

        # Add record of transaction
        current_time = now()
        transaction_type = "buy"
        db.execute("INSERT INTO transactions (userid, transacted, type, name, symbol, price, shares, value, cash) VALUES (?, ?, ?, ?, ?, ?, ?, ?*?, ?-?*?);",
                   userid, current_time, transaction_type, name, symbol, price, shares, shares, price, cash, shares, price)

        # Redirect user to home page
        return redirect("/")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    # Get user's history of transactions
    records = db.execute("SELECT * FROM transactions WHERE userid=?;", session["user_id"])

    # Format money values
    for i, elem in enumerate(records):
        records[i]["price"] = usd(elem["price"])
        records[i]["value"] = usd(elem["value"])
        records[i]["cash"] = usd(elem["cash"])

    return render_template("history.html", records=records)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via GET (as by clicking a link or via redirect)
    if request.method == "GET":
        return render_template("login.html")

    # User reached route via POST (as by submitting a form via POST)
    else:
        # Ensure username was submitted
        username = request.form.get("username")
        if not username:
            return apology("must provide username", 403)

        # Ensure password was submitted
        password = request.form.get("password")
        if not password:
            return apology("must provide password", 403)

        # Query database for username
        records = db.execute("SELECT id, hash FROM users WHERE username=?;", username)

        # Ensure username exists and password is correct
        if len(records) == 0 or not check_password_hash(records[0]["hash"], password):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = records[0]["id"]

        # Redirect user to home page
        return redirect("/")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/login")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""

    # User reached route via GET (as by clicking a link)
    if request.method == "GET":
        return render_template("quote.html")

    # User reached route via POST (as by submitting a form via POST)
    else:
        # Check for symbol
        symbol = request.form.get("symbol")
        if not symbol:
            return apology("must provide symbol")

        # Check for submitted symbol
        quote = lookup(symbol)

        # Check for valid symbol
        if not quote:
            return apology("invalid stock symbol")

        return render_template("quoted.html", name=quote["name"], symbol=quote["symbol"], price=usd(quote["price"]))


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    # User reached route via GET (as by clicking a link)
    if request.method == "GET":
        return render_template("register.html")

    # User reached route via POST (as by submitting a form via POST)
    else:
        # Check for username
        username = request.form.get("username")
        if not username:
            return apology("must provide username")

        # Check for password
        password = request.form.get("password")
        if not password:
            return apology("must provide password")

        # Check for confirmation
        confirmation = request.form.get("confirmation")
        if not confirmation:
            return apology("must confirm password")

        # Check whether username has already been taken
        records = db.execute("SELECT id FROM users WHERE username=?;", username)
        if len(records) == 1:
            return apology("this username has already been taken")

        # Check whether passwords match
        if password != confirmation:
            return apology("passwords do not match")

        # Generate hash of password
        hash = generate_password_hash(password)

        # Register new user
        db.execute("INSERT INTO users (username, hash) VALUES (?, ?);", username, hash)

        return redirect("/login")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    # Save user id
    userid = session["user_id"]

    # Get user data
    user_data = db.execute("SELECT name, symbol, shares FROM shares WHERE userid=?;", userid)

    # User reached route via GET (as by clicking a link)
    if request.method == "GET":
        # Check whether user has any stock at all
        if len(user_data) == 0:
            return apology("have no stock to sell")
        return render_template("sell.html", records=user_data)

    # User reached route via POST (as by submitting a form via POST)
    else:
        # Check for symbol
        symbol = request.form.get("symbol")
        if not symbol:
            return apology("must choose a stock")

        # Check whether user owns of that stock
        symbols = []
        for _, elem in enumerate(user_data):
            symbols.append(elem["symbol"])
        if symbol not in symbols:
            return apology("do not own any" + symbol)

        # Check for shares
        shares = request.form.get("shares")
        if not shares:
            return apology("must specify shares")

        # Check for valid type
        try:
            shares = int(shares)
        except ValueError:
            return apology("shares is of invalid data type")

        # Check for negative value
        if shares < 0:
            return apology("shares must be greater than zero")

        # Save company name and how many shares of stock user owns
        name = ""
        shares_owned = 0
        for _, elem in enumerate(user_data):
            if symbol == elem["symbol"]:
                name = elem["name"]
                shares_owned = elem["shares"]

        # Check whether shares is greater than quantity user owns
        if shares > shares_owned:
            return apology("you only have " + str(shares_owned) + " shares of " + symbol)
        # Check whether shares is equal to quantity user owns
        elif shares == shares_owned:
            db.execute("DELETE FROM shares WHERE userid=? AND symbol=?;", userid, symbol)
        # Subtract shares from quantity user owns and update record
        else:
            db.execute("UPDATE shares SET shares=shares-? WHERE userid=? AND symbol=?;", shares, userid, symbol)

        # Look up for current price of stock
        price = lookup(symbol)["price"]

        # Add value to cash and update record
        db.execute("UPDATE users SET cash=cash+?*? WHERE id=?;", shares, price, userid)

        # Add record of transaction
        current_time = now()
        transaction_type = "sell"
        cash = db.execute("SELECT cash FROM users WHERE id=?;", userid)[0]["cash"]
        db.execute("INSERT INTO transactions (userid, transacted, type, name, symbol, price, shares, value, cash) VALUES (?, ?, ?, ?, ?, ?, ?, ?*?, ?);",
                   userid, current_time, transaction_type, name, symbol, price, shares, shares, price, cash)

        return redirect("/")

if __name__ == '__main__':
    app.run(debug=True, port=os.getenv("PORT", default=5000))
