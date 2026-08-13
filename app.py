from flask import Flask, request, redirect, session, send_from_directory, jsonify
from markupsafe import escape
from werkzeug.security import generate_password_hash, check_password_hash
from pathlib import Path
import json
import os

app = Flask(__name__)

app.secret_key = os.environ.get(
    "TASKBRIGHT_SECRET",
    "taskbright-development-secret-change-later"
)

BASE_DIR = Path(__file__).resolve().parent
VIEWS_DIR = BASE_DIR / "views"
DATA_DIR = BASE_DIR / "data"
USERS_FILE = DATA_DIR / "users.json"
DEPOSITS_FILE = DATA_DIR / "deposits.json"
AIRTIME_FILE = DATA_DIR / "airtime.json"
DEPOSIT_UPLOADS = BASE_DIR / "public" / "uploads" / "deposits"
DEPOSIT_UPLOADS.mkdir(parents=True, exist_ok=True)
SUBMISSION_UPLOADS = BASE_DIR / "public" / "uploads" / "submissions"
SUBMISSION_UPLOADS.mkdir(parents=True, exist_ok=True)

DATA_DIR.mkdir(exist_ok=True)



@app.route("/css/<path:filename>")
def css(filename):
    return send_from_directory(BASE_DIR / "public" / "css", filename)

def load_users():
    if not USERS_FILE.exists():
        return []

    try:
        return json.loads(USERS_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return []


def save_users(users):
    USERS_FILE.write_text(
        json.dumps(users, indent=2)
    )


def current_user():
    user_id = session.get("user_id")

    if not user_id:
        return None

    for user in load_users():
        if user.get("id") == user_id:
            return user

    return None


@app.route("/")
def home():
    return send_from_directory(VIEWS_DIR, "index.html")


@app.route("/register.html")
def register_page():
    page = (VIEWS_DIR / "register.html").read_text()
    referral = request.args.get("ref", "").strip().upper()
    page = page.replace(
        'id="referral_code"',
        f'id="referral_code" value="{escape(referral)}"',
        1
    )
    return page

@app.route("/register", methods=["POST"])
def register():
    first_name = request.form.get("first_name", "").strip()
    last_name = request.form.get("last_name", "").strip()
    email = request.form.get("email", "").strip().lower()
    phone = request.form.get("phone", "").strip()
    password = request.form.get("password", "")
    confirm_password = request.form.get("confirm_password", "")
    referral_code = request.form.get("referral_code", "").strip()

    if not all([first_name, last_name, email, phone, password]):
        return "Please complete all required fields.", 400

    if password != confirm_password:
        return "Passwords do not match.", 400

    users = load_users()

    if any(user["email"] == email for user in users):
        return "An account with this email already exists. Please log in.", 409

    user_id = max(
        [user.get("id", 0) for user in users],
        default=0
    ) + 1

    # Generate a unique referral code for this user.
    import secrets
    import string

    existing_codes = {
        str(user.get("referral_code", "")).strip().upper()
        for user in users
        if user.get("referral_code")
    }

    while True:
        generated_referral_code = "TB" + "".join(
            secrets.choice(string.ascii_uppercase + string.digits)
            for _ in range(6)
        )
        if generated_referral_code not in existing_codes:
            break

    user = {
        "id": user_id,
        "first_name": first_name,
        "last_name": last_name,
        "email": email,
        "phone": phone,
        "password": generate_password_hash(password),
        "referral_code": generated_referral_code,
        "referred_by": referral_code,
        "deposit_balance": 0,
        "task_wallet": 0,
        "referral_wallet": 0,
        "activated": False
    }

    users.append(user)
    save_users(users)

    session.clear()
    session["user_id"] = user_id

    return redirect("/dashboard.html")


@app.route("/login", methods=["POST"])
def login():
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    user = next(
        (
            user for user in load_users()
            if user.get("email") == email
        ),
        None
    )

    if not user or not check_password_hash(
        user.get("password", ""),
        password
    ):
        return "Invalid email or password.", 401

    session.clear()
    session["user_id"] = user["id"]

    return redirect("/dashboard.html")



TASKS_FILE = DATA_DIR / "tasks.json"

def load_tasks():
    if not TASKS_FILE.exists():
        return []
    try:
        return json.loads(TASKS_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return []

def save_tasks(tasks):
    TASKS_FILE.write_text(json.dumps(tasks, indent=2))


@app.route("/dashboard.html")
def dashboard():
    user = current_user()

    if not user:
        return redirect("/login.html")

    page = (VIEWS_DIR / "dashboard.html").read_text()

    deposit_balance = float(user.get("deposit_balance", 0) or 0)
    task_wallet = float(user.get("task_wallet", 0) or 0)
    referral_wallet = float(user.get("referral_wallet", 0) or 0)

    # Replace dedicated placeholders if they exist.
    page = page.replace(
        "{{DEPOSIT_BALANCE}}",
        f"{deposit_balance:,.2f}"
    )
    page = page.replace(
        "{{TASK_WALLET}}",
        f"{task_wallet:,.2f}"
    )
    page = page.replace(
        "{{REFERRAL_WALLET}}",
        f"{referral_wallet:,.2f}"
    )

    return page


@app.route("/create-task", methods=["POST"])
def create_task():
    user = current_user()

    if not user:
        return redirect("/login.html")

    task_type = request.form.get("task_type", "").strip()
    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    link = request.form.get("link", "").strip()
    workers = request.form.get("workers", "").strip()

    try:
        workers = int(workers)
    except ValueError:
        return "Invalid number of workers.", 400

    if workers < 5:
        return "Minimum number of workers is 5.", 400

    pricing = {
        "telegram_bot": {
            "total": 60,
            "reward": 35,
            "fee": 25
        },
        "whatsapp_telegram": {
            "total": 14,
            "reward": 8,
            "fee": 6
        },
        "custom": {
            "total": 85,
            "reward": 45,
            "fee": 40
        },
        "app_install": {
            "total": 100,
            "reward": 60,
            "fee": 40
        },
        "youtube_subscribers": {
            "total": 20,
            "reward": 10,
            "fee": 10
        },
        "facebook_followers": {
            "total": 14,
            "reward": 7,
            "fee": 7
        },
        "website_signups": {
            "total": 35,
            "reward": 20,
            "fee": 15
        },
        "instagram_followers": {
            "total": 13,
            "reward": 7,
            "fee": 6
        },
        "tiktok_followers": {
            "total": 13,
            "reward": 7,
            "fee": 6
        },
        "social_likes": {
            "total": 10,
            "reward": 5,
            "fee": 5
        },
        "social_comments": {
            "total": 13,
            "reward": 6,
            "fee": 7
        }
    }

    task_pricing = pricing.get(task_type)

    if task_pricing is None:
        return "Invalid task type.", 400

    cost_per_worker = task_pricing["total"]
    worker_reward = task_pricing["reward"]
    website_fee = task_pricing["fee"]

    total_cost = cost_per_worker * workers

    users = load_users()

    for stored_user in users:
        if stored_user.get("id") == user.get("id"):
            balance = float(stored_user.get("deposit_balance", 0))

            if balance < total_cost:
                return (
                    f"Insufficient Deposit Balance. "
                    f"You need ₦{total_cost:,.0f}.",
                    400
                )

            stored_user["deposit_balance"] = round(
                balance - total_cost, 2
            )

            tasks = load_tasks()

            tasks.append({
                "id": os.urandom(8).hex(),
                "creator_id": stored_user.get("id"),
                "creator_name": (
                    f"{stored_user.get('first_name', '')} "
                    f"{stored_user.get('last_name', '')}"
                ).strip(),
                "task_type": task_type,
                "title": title,
                "description": description,
                "link": link,
                "workers": workers,
                "cost_per_worker": cost_per_worker,
                "worker_reward": worker_reward,
                "website_fee": website_fee,
                "total_cost": total_cost,
                "submitted": 0,
                "approved": 0,
                "status": "Active"
            })

            save_users(users)
            save_tasks(tasks)

            return redirect("/my-tasks.html")

    return "User account not found.", 404


def load_deposits():
    if not DEPOSITS_FILE.exists():
        return []
    try:
        return json.loads(DEPOSITS_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return []

def save_deposits(deposits):
    DEPOSITS_FILE.write_text(json.dumps(deposits, indent=2))


@app.route("/deposit", methods=["POST"])
def submit_deposit():
    user = current_user()

    if not user:
        return redirect("/login.html")

    try:
        amount = float(request.form.get("amount", "0"))
    except ValueError:
        return "Invalid deposit amount.", 400

    if amount < 200:
        return "Minimum deposit is ₦200.", 400

    payment_method = request.form.get("payment_method", "").strip()
    sender_name = request.form.get("sender_name", "").strip()
    screenshot = request.files.get("screenshot")

    if not payment_method or not sender_name:
        return "Please complete all deposit details.", 400

    if not screenshot or not screenshot.filename:
        return "Transaction screenshot is required.", 400

    extension = Path(screenshot.filename).suffix.lower()

    if extension not in {".jpg", ".jpeg", ".png", ".webp"}:
        return "Only JPG, JPEG, PNG and WEBP screenshots are allowed.", 400

    deposits = load_deposits()

    deposit_id = os.urandom(8).hex()
    filename = f"{deposit_id}{extension}"

    screenshot.save(DEPOSIT_UPLOADS / filename)

    deposits.append({
        "id": deposit_id,
        "user_id": user.get("id"),
        "user_name": (
            f"{user.get('first_name', '')} "
            f"{user.get('last_name', '')}"
        ).strip(),
        "amount": amount,
        "payment_method": payment_method,
        "sender_name": sender_name,
        "screenshot": f"/uploads/deposits/{filename}",
        "status": "Pending"
    })

    save_deposits(deposits)

    return redirect("/deposit.html")


@app.route("/deposit-history")
def deposit_history():
    user = current_user()

    if not user:
        return jsonify([])

    deposits = [
        d for d in load_deposits()
        if str(d.get("user_id")) == str(user.get("id"))
    ]

    return jsonify(list(reversed(deposits)))


@app.route("/admin-deposits.html")
def admin_deposits():
    if not session.get("admin"):
        return redirect("/admin-login.html")

    page = (VIEWS_DIR / "admin-deposits.html").read_text()
    deposits = load_deposits()
    cards = ""

    for d in reversed(deposits):
        if d.get("status") != "Pending":
            continue

        cards += f"""
        <article class="admin-request-card">

          <div class="request-header">
            <div>
              <span class="pending-status">Pending</span>
              <h2>₦{d.get("amount", 0):,.0f} Deposit</h2>
            </div>
          </div>

          <div class="request-details">
            <div>
              <span>User</span>
              <strong>{d.get("user_name", "User")}</strong>
            </div>

            <div>
              <span>Payment Method</span>
              <strong>{d.get("payment_method", "")}</strong>
            </div>

            <div>
              <span>Sender Name</span>
              <strong>{d.get("sender_name", "")}</strong>
            </div>
          </div>

          <div class="transaction-proof">
            📸
            <a href="{d.get("screenshot", "#")}" target="_blank">
              View Transaction Screenshot
            </a>
          </div>

          <div class="admin-review-actions">

            <form method="POST" action="/admin-review-deposit">
              <input type="hidden" name="deposit_id"
                     value="{d.get("id")}">
              <input type="hidden" name="decision"
                     value="approve">
              <button class="approve-btn" type="submit">
                ✓ Approve Deposit
              </button>
            </form>

            <form method="POST" action="/admin-review-deposit">
              <input type="hidden" name="deposit_id"
                     value="{d.get("id")}">
              <input type="hidden" name="decision"
                     value="reject">
              <button class="reject-btn" type="submit">
                ✕ Reject Deposit
              </button>
            </form>

          </div>

        </article>
        """

    if not cards:
        cards = """
        <div class="empty-tasks">
          <div class="empty-icon">✓</div>
          <h2>No pending deposits</h2>
          <p>New deposit requests will appear here.</p>
        </div>
        """

    start = page.find('<section class="admin-request-list">')

    if start != -1:
        end = page.find("</section>", start)

        if end != -1:
            page = (
                page[:start]
                + '<section class="admin-request-list">'
                + cards
                + "</section>"
                + page[end + len("</section>"):]
            )

    return page


@app.route("/admin-review-deposit", methods=["POST"])
def admin_review_deposit():
    if not session.get("admin"):
        return redirect("/admin-login.html")

    deposit_id = request.form.get("deposit_id", "").strip()
    decision = request.form.get("decision", "").strip()

    if decision not in ("approve", "reject"):
        return "Invalid decision.", 400

    deposits = load_deposits()

    deposit = next(
        (d for d in deposits if d.get("id") == deposit_id),
        None
    )

    if not deposit:
        return "Deposit not found.", 404

    if deposit.get("status") != "Pending":
        return "This deposit has already been reviewed.", 400

    if decision == "reject":
        deposit["status"] = "Rejected"

    else:
        users = load_users()

        user = next(
            (
                u for u in users
                if u.get("id") == deposit.get("user_id")
            ),
            None
        )

        if not user:
            return "User not found.", 404

        amount = float(deposit.get("amount", 0))

        user["deposit_balance"] = round(
            float(user.get("deposit_balance", 0)) + amount,
            2
        )

        deposit["status"] = "Approved"

        save_users(users)

    save_deposits(deposits)

    return redirect("/admin-deposits.html")


@app.route("/activate", methods=["GET", "POST"])
def activate():
    user = current_user()

    if not user:
        return redirect("/login.html")

    if user.get("activated", False):
        return redirect("/dashboard.html")

    if request.method == "GET":
        return send_from_directory(VIEWS_DIR, "activate.html")

    users = load_users()

    stored_user = next(
        (u for u in users if u.get("id") == user.get("id")),
        None
    )

    if not stored_user:
        return "User account not found.", 404

    balance = float(stored_user.get("deposit_balance", 0))

    if balance < 300:
        page = (VIEWS_DIR / "activate.html").read_text()

        error = """
        <div class="activation-error">
          ⚠️ <strong>Insufficient Deposit Balance</strong>
          <p>
            You need at least ₦300 in your Deposit Balance
            to activate your account.
          </p>
          <a href="/deposit.html" class="secondary-btn">
            Deposit Funds
          </a>
        </div>
        """

        marker = '<form method="POST" action="/activate">'

        if marker in page:
            page = page.replace(marker, error + marker, 1)

        return page, 400

    stored_user["deposit_balance"] = round(balance - 300, 2)
    stored_user["activated"] = True
    stored_user["task_wallet"] = round(
        float(stored_user.get("task_wallet", 0)) + 100,
        2
    )

    # Pay referral rewards once when this user activates.
    if not stored_user.get("referral_reward_paid", False):
        used_code = str(
            stored_user.get("referred_by", "")
        ).strip().upper()

        if used_code:
            referrer = next(
                (
                    u for u in users
                    if str(
                        u.get("referral_code", "")
                    ).strip().upper() == used_code
                    and u.get("id") != stored_user.get("id")
                ),
                None
            )

            if referrer:
                referrer["referral_wallet"] = round(
                    float(
                        referrer.get("referral_wallet", 0)
                    ) + 100,
                    2
                )

                stored_user["referral_wallet"] = round(
                    float(
                        stored_user.get("referral_wallet", 0)
                    ) + 100,
                    2
                )

                stored_user["referral_reward_paid"] = True

    save_users(users)

    return redirect("/dashboard.html")


@app.route("/task-details.html")
def task_details():
    user = current_user()

    if not user:
        return redirect("/login.html")

    if not user.get("activated", False):
        return redirect("/activate")

    task_id = request.args.get("id", "").strip()

    if not task_id:
        return redirect("/tasks.html")

    tasks = load_tasks()

    task = next(
        (t for t in tasks if str(t.get("id")) == str(task_id)),
        None
    )

    if not task:
        return "Task not found.", 404

    if task.get("status", "Active") != "Active":
        return "This task is no longer available.", 400

    if str(task.get("creator_id")) == str(user.get("id")):
        return "You cannot perform your own task.", 403

    from markupsafe import escape

    page = (VIEWS_DIR / "task-details.html").read_text()

    title = task.get("title") or str(
        task.get("task_type", "Task")
    ).replace("_", " ").title()

    reward = float(task.get("worker_reward", task.get("cost_per_worker", 0)) or 0)
    workers = int(task.get("workers", 0) or 0)
    description = task.get("description", "")
    link = task.get("link", "")

    replacements = {
        "{{TASK_ID}}": str(task.get("id", "")),
        "{{TASK_TITLE}}": str(escape(title)),
        "{{TASK_REWARD}}": f"₦{reward:,.2f}",
        "{{TASK_WORKERS}}": str(workers),
        "{{TASK_DESCRIPTION}}": str(escape(description)),
        "{{TASK_LINK}}": str(escape(link)),
    }

    for key, value in replacements.items():
        page = page.replace(key, value)

    return page


@app.route("/perform-task.html")
def perform_task():
    user = current_user()

    if not user:
        return redirect("/login.html")

    if not user.get("activated", False):
        return redirect("/activate")

    task_id = request.args.get("id", "").strip()

    if not task_id:
        return redirect("/tasks.html")

    tasks = load_tasks()

    task = next(
        (t for t in tasks if str(t.get("id")) == str(task_id)),
        None
    )

    if not task:
        return "Task not found.", 404

    if task.get("status", "Active") != "Active":
        return "This task is no longer available.", 400

    if str(task.get("creator_id")) == str(user.get("id")):
        return "You cannot perform your own task.", 403

    from markupsafe import escape

    page = (VIEWS_DIR / "perform-task.html").read_text()

    title = task.get("title") or str(
        task.get("task_type", "Task")
    ).replace("_", " ").title()

    description = task.get("description", "")
    link = str(task.get("link", "") or "").strip()
    if link and not link.startswith(("http://", "https://")):
        link = "https://" + link
    reward = float(task.get("worker_reward", task.get("cost_per_worker", 0)) or 0)
    workers = int(task.get("workers", 0) or 0)

    page = page.replace("{{TASK_ID}}", str(task.get("id", "")))
    page = page.replace("{{TASK_TITLE}}", str(escape(title)))
    page = page.replace("{{TASK_REWARD}}", f"{reward:,.2f}")
    page = page.replace("{{TASK_WORKERS}}", str(workers))
    page = page.replace("{{TASK_DESCRIPTION}}", str(escape(description)))
    page = page.replace("{{TASK_LINK}}", str(escape(link)))

    return page


@app.route("/admin-login", methods=["POST"])
def admin_login():
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    if email != "admin@taskbright.com" or password != "Admin@9090":
        return "Invalid admin email or password.", 401

    session.clear()
    session["admin"] = True

    return redirect("/admin-dashboard.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login.html")



AIRTIME_FILE = DATA_DIR / "airtime_requests.json"


def load_airtime_requests():
    if not AIRTIME_FILE.exists():
        return []

    try:
        return json.loads(AIRTIME_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return []


def save_airtime_requests(requests):
    AIRTIME_FILE.write_text(json.dumps(requests, indent=2))


@app.route("/airtime", methods=["POST"])
def airtime_request():
    user = current_user()

    if not user:
        return redirect("/login.html")

    if not user.get("activated", False):
        return redirect("/activate")

    network = request.form.get("network", "").strip()
    phone = request.form.get("phone", "").strip()
    amount_raw = request.form.get("amount", "").strip()
    wallet = request.form.get("wallet", "").strip()

    if network not in ["MTN", "Airtel", "GLO", "9mobile"]:
        return "Invalid network.", 400

    if not phone.isdigit() or len(phone) != 11:
        return "Enter a valid 11-digit phone number.", 400

    try:
        amount = float(amount_raw)
    except ValueError:
        return "Invalid amount.", 400

    if amount < 100:
        return "Minimum airtime purchase is ₦100.", 400

    if wallet not in ["task", "referral"]:
        return "Select a valid wallet.", 400

    wallet_key = "task_wallet" if wallet == "task" else "referral_wallet"
    available_balance = float(user.get(wallet_key, 0) or 0)

    if available_balance < amount:
        return (
            f"Insufficient balance. Available balance is ₦{available_balance:,.2f}.",
            400
        )

    requests = load_airtime_requests()

    airtime_id = str(max(
        [int(x.get("id", 0)) for x in requests if str(x.get("id", "")).isdigit()] or [0]
    ) + 1)

    airtime = {
        "id": airtime_id,
        "user_id": user["id"],
        "name": f'{user.get("first_name", "")} {user.get("last_name", "")}'.strip(),
        "email": user.get("email", ""),
        "network": network,
        "phone": phone,
        "amount": round(amount, 2),
        "wallet": wallet,
        "status": "Pending"
    }

    requests.append(airtime)
    save_airtime_requests(requests)

    return redirect("/airtime-history.html")


@app.route("/airtime-history.html")
def airtime_history():
    user = current_user()

    if not user:
        return redirect("/login.html")

    requests = [
        item for item in load_airtime_requests()
        if item.get("user_id") == user.get("id")
    ]

    history_html = (VIEWS_DIR / "airtime-history.html").read_text()

    cards = ""

    for item in reversed(requests):
        status = item.get("status", "Pending")

        cards += f"""
        <article class="admin-request-card airtime-history-card">
          <div class="request-header">
            <div>
              <span class="pending-status">{status}</span>
              <h2>₦{float(item.get("amount", 0)):,.0f} Airtime</h2>
            </div>
          </div>

          <div class="request-details">
            <div>
              <span>Network</span>
              <strong>{item.get("network", "")}</strong>
            </div>

            <div>
              <span>Phone Number</span>
              <strong>{item.get("phone", "")}</strong>
            </div>

            <div>
              <span>Wallet</span>
              <strong>{item.get("wallet", "").title()} Wallet</strong>
            </div>

            <div>
              <span>Status</span>
              <strong>{status}</strong>
            </div>
          </div>
        </article>
        """

    if not cards:
        cards = """
        <div class="empty-tasks">
          <div class="empty-icon">📱</div>
          <h2>No airtime requests yet</h2>
          <p>Your airtime requests will appear here after you make a purchase.</p>
        </div>
        """

    history_html = history_html.replace(
        '<section class="airtime-history-list" id="airtimeHistory">',
        '<section class="airtime-history-list" id="airtimeHistory">' + cards,
        1
    )

    return history_html


@app.route("/airtime-history-data")
def airtime_history_data():
    user = current_user()

    if not user:
        return json.dumps({"error": "Not logged in"}), 401, {
            "Content-Type": "application/json"
        }

    requests = [
        item for item in load_airtime_requests()
        if str(item.get("user_id")) == str(user.get("id"))
    ]

    return json.dumps(requests), 200, {
        "Content-Type": "application/json"
    }


@app.route("/admin/airtime/<request_id>/<action>", methods=["POST"])
def admin_airtime_action(request_id, action):
    if not session.get("admin"):
        return redirect("/admin-login.html")

    if action not in ["approve", "reject"]:
        return "Invalid action.", 400

    requests = load_airtime_requests()

    target = next(
        (item for item in requests if str(item.get("id")) == str(request_id)),
        None
    )

    if not target:
        return "Airtime request not found.", 404

    if target.get("status") != "Pending":
        return "This request has already been reviewed.", 400

    if action == "reject":
        target["status"] = "Rejected"
        save_airtime_requests(requests)
        return redirect("/admin-airtime.html")

    users = load_users()

    stored_user = next(
        (u for u in users if u.get("id") == target.get("user_id")),
        None
    )

    if not stored_user:
        return "User account not found.", 404

    wallet_key = "task_wallet" if target["wallet"] == "task" else "referral_wallet"
    balance = float(stored_user.get(wallet_key, 0))
    amount = float(target["amount"])

    if balance < amount:
        return "User does not have enough wallet balance to approve this request.", 400

    stored_user[wallet_key] = round(balance - amount, 2)
    target["status"] = "Approved"

    save_users(users)
    save_airtime_requests(requests)

    return redirect("/admin-airtime.html")


@app.route("/admin-airtime.html")
def admin_airtime():
    if not session.get("admin"):
        return redirect("/admin-login.html")

    requests = load_airtime_requests()

    page = (VIEWS_DIR / "admin-airtime.html").read_text()

    cards = ""

    for item in reversed(requests):
        status = item.get("status", "Pending")

        if status != "Pending":
            continue

        cards += f"""
        <article class="admin-request-card">

          <div class="request-header">
            <div>
              <span class="pending-status">Pending</span>
              <h2>₦{float(item.get("amount", 0)):,.0f} Airtime</h2>
            </div>
          </div>

          <div class="request-details">

            <div>
              <span>User</span>
              <strong>{item.get("name", "User")}</strong>
            </div>

            <div>
              <span>Network</span>
              <strong>{item.get("network", "")}</strong>
            </div>

            <div>
              <span>Phone number</span>
              <strong>{item.get("phone", "")}</strong>
            </div>

            <div>
              <span>Amount</span>
              <strong>₦{float(item.get("amount", 0)):,.0f}</strong>
            </div>

            <div>
              <span>Pay from</span>
              <strong>{item.get("wallet", "").title()} Wallet</strong>
            </div>

          </div>

          <div class="admin-review-actions">

            <form method="POST"
                  action="/admin/airtime/{item.get('id')}/approve">
              <button type="submit" class="approve-btn">
                ✓ Approve Airtime
              </button>
            </form>

            <form method="POST"
                  action="/admin/airtime/{item.get('id')}/reject">
              <button type="submit" class="reject-btn">
                ✕ Reject Airtime
              </button>
            </form>

          </div>

        </article>
        """

    if not cards:
        cards = """
        <div class="empty-tasks">
          <div class="empty-icon">📱</div>
          <h2>No pending airtime requests</h2>
          <p>New user requests will appear here when submitted.</p>
        </div>
        """

    marker = '<section class="admin-request-list">'

    start = page.find(marker)
    if start != -1:
        end = page.find('</section>', start)

        if end != -1:
            page = (
                page[:start]
                + marker
                + cards
                + '</section>'
                + page[end + len('</section>'):]
            )

    return page


@app.route("/uploads/<path:filename>")
def uploads(filename):
    return send_from_directory(
        BASE_DIR / "public" / "uploads",
        filename
    )


@app.route("/tasks.html")
def tasks():
    user = current_user()

    if not user:
        return redirect("/login.html")

    if not user.get("activated", False):
        return redirect("/activate")

    tasks = load_tasks()
    submissions = load_submissions()
    submitted_task_ids = {
        str(x.get("task_id"))
        for x in submissions
        if str(x.get("worker_id")) == str(user.get("id"))
    }

    cards = ""

    for task in reversed(tasks):
        if task.get("status") != "Active":
            continue

        if task.get("creator_id") == user.get("id"):
            continue
        if str(task.get("id")) in submitted_task_ids:
            continue

        cards += f"""
        <article class="market-task-card">

          <div class="market-task-top">
            <div>
              <span class="task-category">
                {task.get("task_type", "Other").replace("_", " ").title()}
              </span>
              <h2>{task.get("title", "Task")}</h2>
            </div>

            <strong>₦{task.get("worker_reward", task.get("cost_per_worker", 0)):,}</strong>
          </div>

          <p>{task.get("description", "")}</p>

          <div class="market-task-info">
            <span>👥 {task.get("workers", 0)} workers</span>
            <span>📸 Proof required</span>
          </div>

          <a href="/task-details.html?id={task.get("id")}"
             class="primary-btn full-btn">
            View & Perform Task
          </a>

        </article>
        """

    if not cards:
        cards = """
        <div class="empty-tasks">
          <div class="empty-icon">✓</div>
          <h2>No tasks available</h2>
          <p>Tasks created by users will appear here when they become available.</p>
        </div>
        """

    page = (VIEWS_DIR / "tasks.html").read_text()

    marker = '<section class="marketplace-list">'

    start = page.find(marker)

    if start != -1:
        end = page.find("</section>", start)

        if end != -1:
            page = (
                page[:start]
                + marker
                + cards
                + "</section>"
                + page[end + len("</section>"):]
            )

    return page


@app.route("/my-submissions.html")
def my_submissions_page():
    user = current_user()
    if not user:
        return redirect("/login.html")

    submissions = load_submissions()
    user_id = str(user.get("id"))

    user_submissions = [
        s for s in submissions
        if str(s.get("worker_id")) == user_id
    ]

    page = (VIEWS_DIR / "my-submissions.html").read_text()

    cards = []

    for s in reversed(user_submissions):
        task_title = s.get("task_title") or "Task"
        status = s.get("status", "Pending")
        proof = s.get("proof", "")
        screenshot = s.get("screenshot", "")
        rejection = s.get("rejection_reason", "")

        cards.append(f"""
        <article class="worker-submission-card">
          <div class="worker-submission-top">
            <div>
              <span class="task-category">Task</span>
              <h2>{escape(str(task_title))}</h2>
            </div>
            <span class="{status.lower()}-status">{escape(status)}</span>
          </div>

          <div class="worker-submission-info">
            <span>Status: <strong>{escape(status)}</strong></span>
          </div>

          <p class="submission-status-text">
            Proof: {escape(str(proof))}
          </p>

          {f'<img src="{escape(str(screenshot))}" style="max-width:100%;border-radius:10px;margin-top:12px;">' if screenshot else ''}

          {f'<p class="submission-status-text">Rejection reason: {escape(str(rejection))}</p>' if rejection else ''}
        </article>
        """)

    if not cards:
        cards.append('<div class="empty-tasks">No submissions yet.</div>')

    page = page.replace("{{SUBMISSION_CARDS}}", "\n".join(cards))
    return page

@app.route("/referrals.html")
def referrals_page():
    user = current_user()
    if not user:
        return redirect("/login.html")

    users = load_users()

    # Give every existing user a permanent referral code.
    changed = False
    existing_codes = {
        str(u.get("referral_code", "")).strip().upper()
        for u in users
        if u.get("referral_code")
    }

    for u in users:
        if not u.get("referral_code"):
            while True:
                code = "TB" + "".join(
                    secrets.choice(string.ascii_uppercase + string.digits)
                    for _ in range(6)
                )
                if code not in existing_codes:
                    break

            u["referral_code"] = code
            existing_codes.add(code)
            changed = True

    if changed:
        save_users(users)

    # Reload the current user so the generated code is available.
    user_id = str(user.get("id"))
    user = next(
        (u for u in users if str(u.get("id")) == user_id),
        user
    )

    code = str(user.get("referral_code", "")).strip().upper()

    referrals = [
        u for u in users
        if str(u.get("referred_by", "")).strip().upper() == code
        and str(u.get("id")) != user_id
    ]

    activated = [
        u for u in referrals
        if u.get("activated", False)
    ]

    earnings = len(activated) * 100

    page = (VIEWS_DIR / "referrals.html").read_text()

    referral_link = (
        request.host_url.rstrip("/")
        + "/register.html?ref="
        + code
    )

    # Replace the entire referral-link input value.
    import re
    page = re.sub(
        r'<input\s+type="text"\s+value="[^"]*"\s+readonly\s*>',
        f'<input type="text" value="{escape(referral_link)}" readonly>',
        page,
        count=1
    )

    # Also expose the actual code if the template has a placeholder.
    page = page.replace("{{REFERRAL_CODE}}", escape(code))
    page = page.replace("{{REFERRAL_LINK}}", escape(referral_link))

    # Statistics.
    page = page.replace(
        "<strong>0</strong>",
        f"<strong>{len(referrals)}</strong>",
        1
    )
    page = page.replace(
        "<strong>0</strong>",
        f"<strong>{len(activated)}</strong>",
        1
    )
    page = page.replace(
        "<strong>₦0</strong>",
        f"<strong>₦{earnings}</strong>",
        1
    )

    return page

@app.route("/<page>")
def page(page):
    if not page.endswith(".html"):
        page += ".html"

    file_path = VIEWS_DIR / page

    if not file_path.is_file():
        return "Page not found", 404

    return send_from_directory(VIEWS_DIR, page)


SUBMISSIONS_FILE = DATA_DIR / "submissions.json"

def load_submissions():
    if not SUBMISSIONS_FILE.exists():
        return []
    try:
        return json.loads(SUBMISSIONS_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return []

def save_submissions(submissions):
    SUBMISSIONS_FILE.write_text(
        json.dumps(submissions, indent=2)
    )


@app.route("/my-tasks.html")
def my_tasks_page():
    user = current_user()
    if not user:
        return redirect("/login.html")

    tasks = load_tasks()
    user_id = str(user.get("id"))

    my_tasks = [
        t for t in tasks
        if str(t.get("creator_id")) == user_id
    ]

    page = (VIEWS_DIR / "my-tasks.html").read_text()

    cards = []

    for task in reversed(my_tasks):
        task_id = task.get("id", "")
        title = task.get("title") or task.get("task_type") or "Task"
        status = task.get("status", "Active")
        workers = int(task.get("workers", 0) or 0)
        submitted = int(task.get("submitted", 0) or 0)

        cards.append(f"""
        <article class="worker-submission-card">
          <div class="worker-submission-top">
            <div>
              <span class="task-category">{escape(str(task.get("task_type", "Task")))}</span>
              <h2>{escape(str(title))}</h2>
            </div>
            <span class="pending-status">{escape(str(status))}</span>
          </div>

          <div class="worker-submission-info">
            <span>Workers: <strong>{workers}</strong></span>
            <span>Submissions: <strong>{submitted}</strong></span>
          </div>

          <a href="/task-submissions.html?task_id={escape(str(task_id))}"
             class="primary-btn full-btn">
            View Worker Submissions
          </a>
        </article>
        """)

    if not cards:
        cards.append("""
        <div class="empty-tasks">
          No created tasks yet.
          <br>
          Your tasks will appear here after you create them.
        </div>
        """)

    page = page.replace("{{TASK_CARDS}}", "\\n".join(cards))
    return page

@app.route("/task-submissions.html")
def task_submissions_page():
    user = current_user()
    if not user:
        return redirect("/login.html")

    task_id = request.args.get("task_id", "").strip()
    if not task_id:
        return redirect("/my-tasks.html")

    tasks = load_tasks()
    task = next(
        (t for t in tasks if str(t.get("id")) == str(task_id)),
        None
    )

    if not task:
        return "Task not found.", 404

    if str(task.get("creator_id")) != str(user.get("id")):
        return "You are not allowed to view these submissions.", 403

    submissions = load_submissions()

    task_submissions = [
        s for s in submissions
        if str(s.get("task_id")) == str(task_id)
        and s.get("status", "Pending") == "Pending"
    ]

    page = (VIEWS_DIR / "task-submissions.html").read_text()

    cards = []

    for s in reversed(task_submissions):
        status = s.get("status", "Pending")
        proof = s.get("proof", "")
        screenshot = s.get("screenshot", "")
        worker_name = s.get("worker_name", "Worker")
        submission_id = s.get("id", "")

        buttons = ""

        if status == "Pending":
            buttons = f"""
            <div style="display:flex;gap:10px;margin-top:15px;">
              <form method="POST" action="/review-submission">
                <input type="hidden" name="submission_id" value="{escape(str(submission_id))}">
                <input type="hidden" name="decision" value="approve">
                <button type="submit" class="primary-btn">Approve</button>
              </form>

              <form method="POST" action="/review-submission">
                <input type="hidden" name="submission_id" value="{escape(str(submission_id))}">
                <input type="hidden" name="decision" value="reject">
                <button type="submit" class="primary-btn">Reject</button>
              </form>
            </div>
            """

        cards.append(f"""
        <article class="worker-submission-card">
          <div class="worker-submission-top">
            <div>
              <span class="task-category">Worker</span>
              <h2>{escape(str(worker_name))}</h2>
            </div>
            <span class="{status.lower()}-status">{escape(str(status))}</span>
          </div>

          <div class="worker-submission-info">
            <span>Task: <strong>{escape(str(task.get("title") or task.get("task_type") or "Task"))}</strong></span>
            <span>Reward: <strong>₦{float(task.get("worker_reward", task.get("cost_per_worker", 0)) or 0):,.2f}</strong></span>
          </div>

          <p class="submission-status-text">
            <strong>Proof:</strong> {escape(str(proof))}
          </p>

          {f'<img src="{escape(str(screenshot))}" style="max-width:100%;height:auto;border-radius:10px;margin-top:12px;">' if screenshot else ''}

          {buttons}
        </article>
        """)

    if not cards:
        cards.append('<div class="empty-tasks">No worker submissions yet.</div>')

    page = page.replace("{{SUBMISSION_CARDS}}", "\\n".join(cards))
    page = page.replace("{{TASK_TITLE}}", escape(str(task.get("title") or task.get("task_type") or "Task")))

    return page

@app.route("/review-submission", methods=["POST"])
def review_submission():
    user = current_user()

    if not user:
        return redirect("/login.html")

    if not user.get("activated", False):
        return redirect("/activate")

    submission_id = request.form.get("submission_id", "").strip()
    decision = request.form.get("decision", "").strip().lower()

    if decision not in ("approve", "reject"):
        return "Invalid decision.", 400

    submissions = load_submissions()

    submission = next(
        (
            x for x in submissions
            if str(x.get("id")) == str(submission_id)
        ),
        None
    )

    if not submission:
        return "Submission not found.", 404

    # Only the task creator can review the submission.
    if str(submission.get("creator_id")) != str(user.get("id")):
        return "You are not allowed to review this submission.", 403

    if submission.get("status") != "Pending":
        return "This submission has already been reviewed.", 400

    if decision == "reject":
        submission["status"] = "Rejected"
        save_submissions(submissions)
        return redirect(
            "/task-submissions.html?task_id="
            + str(submission.get("task_id"))
        )

    # APPROVE
    submission["status"] = "Approved"

    tasks = load_tasks()

    task = next(
        (
            t for t in tasks
            if str(t.get("id")) == str(submission.get("task_id"))
        ),
        None
    )

    if not task:
        return "Task not found.", 404

    # Pay the worker from the task reward.
    worker_id = submission.get("worker_id")
    worker_reward = float(
        task.get("worker_reward", task.get("cost_per_worker", 0)) or 0
    )

    users = load_users()

    worker = next(
        (
            u for u in users
            if str(u.get("id")) == str(worker_id)
        ),
        None
    )

    if not worker:
        return "Worker account not found.", 404

    worker["task_wallet"] = round(
        float(worker.get("task_wallet", 0) or 0) + worker_reward,
        2
    )

    task["approved"] = int(task.get("approved", 0)) + 1

    save_users(users)
    save_tasks(tasks)
    save_submissions(submissions)

    return redirect(
        "/task-submissions.html?task_id="
        + str(submission.get("task_id"))
    )


@app.route("/submit-task", methods=["POST"])
def submit_task():
    user = current_user()

    if not user:
        return redirect("/login.html")

    if not user.get("activated", False):
        return redirect("/activate")

    task_id = request.form.get("task_id", "").strip()
    proof = request.form.get("proof", "").strip()
    screenshot = request.files.get("screenshot")

    if not task_id:
        return "Task ID is required.", 400

    if not proof:
        return "Please enter your proof.", 400

    if not screenshot or not screenshot.filename:
        return "Screenshot proof is required.", 400

    extension = Path(screenshot.filename).suffix.lower()

    if extension not in {".jpg", ".jpeg", ".png", ".webp"}:
        return "Only JPG, JPEG, PNG and WEBP screenshots are allowed.", 400

    tasks = load_tasks()

    task = next(
        (t for t in tasks if str(t.get("id")) == str(task_id)),
        None
    )

    if not task:
        return "Task not found.", 404

    if task.get("status", "Active") != "Active":
        return "This task is no longer active.", 400

    if str(task.get("creator_id")) == str(user.get("id")):
        return "You cannot submit your own task.", 403

    submissions = load_submissions()

    submission_id = os.urandom(8).hex()
    filename = f"{submission_id}{extension}"

    screenshot.save(SUBMISSION_UPLOADS / filename)

    submission = {
        "id": submission_id,
        "task_id": task.get("id"),
        "task_title": task.get("title", "Task"),
        "creator_id": task.get("creator_id"),
        "worker_id": user.get("id"),
        "worker_name": (
            f'{user.get("first_name", "")} '
            f'{user.get("last_name", "")}'
        ).strip(),
        "worker_email": user.get("email", ""),
        "proof": proof,
        "screenshot": f"/uploads/submissions/{filename}",
        "status": "Pending"
    }

    submissions.append(submission)
    save_submissions(submissions)

    task["submitted"] = int(task.get("submitted", 0)) + 1
    save_tasks(tasks)

    return redirect("/tasks.html")



WITHDRAWALS_FILE = DATA_DIR / "withdrawals.json"


def load_withdrawals():
    if not WITHDRAWALS_FILE.exists():
        return []

    try:
        return json.loads(WITHDRAWALS_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return []


def save_withdrawals(withdrawals):
    WITHDRAWALS_FILE.write_text(
        json.dumps(withdrawals, indent=2)
    )


@app.route("/withdraw", methods=["POST"])
def withdraw():
    user = current_user()

    if not user:
        return redirect("/login.html")

    if not user.get("activated", False):
        return redirect("/activate")

    wallet = request.form.get("wallet", "").strip()
    amount_raw = request.form.get("amount", "").strip()
    bank_name = request.form.get("bank_name", "").strip()
    account_number = request.form.get("account_number", "").strip()
    account_name = request.form.get("account_name", "").strip()

    if wallet not in ("task", "referral"):
        return "Select a valid wallet.", 400

    try:
        amount = float(amount_raw)
    except (ValueError, TypeError):
        return "Invalid amount.", 400

    minimum = 350 if wallet == "task" else 300
    maximum = 5000 if wallet == "task" else 7000

    if amount < minimum:
        return redirect(f"/withdraw.html?error=Minimum%20withdrawal%20is%20₦{minimum:,}.")

    if amount > maximum:
        return redirect(f"/withdraw.html?error=Maximum%20withdrawal%20is%20₦{maximum:,}.")

    wallet_key = "task_wallet" if wallet == "task" else "referral_wallet"
    available_balance = float(user.get(wallet_key, 0) or 0)

    if available_balance < amount:
        return redirect("/withdraw.html?error=insufficient")

    if not bank_name:
        return "Bank name is required.", 400

    if not account_number.isdigit() or len(account_number) != 10:
        return "Enter a valid 10-digit account number.", 400

    if not account_name:
        return "Account name is required.", 400

    withdrawals = load_withdrawals()

    withdrawal_id = str(max(
        [
            int(x.get("id", 0))
            for x in withdrawals
            if str(x.get("id", "")).isdigit()
        ] or [0]
    ) + 1)

    withdrawal = {
        "id": withdrawal_id,
        "user_id": user.get("id"),
        "name": f'{user.get("first_name", "")} {user.get("last_name", "")}'.strip(),
        "email": user.get("email", ""),
        "wallet": wallet,
        "amount": round(amount, 2),
        "bank_name": bank_name,
        "account_number": account_number,
        "account_name": account_name,
        "status": "Pending"
    }

    withdrawals.append(withdrawal)
    save_withdrawals(withdrawals)

    return redirect("/withdraw.html")


@app.route("/withdrawal-history")
def withdrawal_history():
    user = current_user()

    if not user:
        return "", 401

    withdrawals = [
        item for item in load_withdrawals()
        if str(item.get("user_id")) == str(user.get("id"))
    ]

    cards = []

    for item in reversed(withdrawals):
        status = str(item.get("status", "Pending"))

        cards.append(f"""
        <article class="admin-request-card airtime-history-card">
          <div class="request-header">
            <div>
              <span class="pending-status">{status}</span>
              <h2>₦{float(item.get("amount", 0) or 0):,.0f} Withdrawal</h2>
            </div>
          </div>

          <div class="request-details">
            <div>
              <span>Wallet</span>
              <strong>{str(item.get("wallet", "")).title()} Wallet</strong>
            </div>

            <div>
              <span>Bank</span>
              <strong>{item.get("bank_name", "")}</strong>
            </div>

            <div>
              <span>Account</span>
              <strong>{item.get("account_number", "")}</strong>
            </div>

            <div>
              <span>Status</span>
              <strong>{status}</strong>
            </div>
          </div>
        </article>
        """)

    return "\n".join(cards)


@app.route("/admin-withdrawals.html")
def admin_withdrawals_page():
    if not session.get("admin"):
        return redirect("/admin-login.html")

    page = (VIEWS_DIR / "admin-withdrawals.html").read_text()

    withdrawals = load_withdrawals()
    cards = []

    for item in reversed(withdrawals):
        status = str(item.get("status", "Pending"))
        withdrawal_id = str(item.get("id", ""))

        buttons = ""

        if status == "Pending":
            buttons = f"""
            <div style="display:flex;gap:10px;margin-top:15px;">
              <form method="POST" action="/admin/withdrawal/{withdrawal_id}/approve">
                <button type="submit" class="primary-btn">Approve</button>
              </form>

              <form method="POST" action="/admin/withdrawal/{withdrawal_id}/reject">
                <button type="submit" class="primary-btn">Reject</button>
              </form>
            </div>
            """

        cards.append(f"""
        <article class="worker-submission-card">
          <div class="worker-submission-top">
            <div>
              <span class="task-category">Withdrawal</span>
              <h2>{item.get("name", "User")}</h2>
            </div>
            <span class="{status.lower()}-status">{status}</span>
          </div>

          <div class="worker-submission-info">
            <span>Amount: <strong>₦{float(item.get("amount", 0) or 0):,.2f}</strong></span>
            <span>Wallet: <strong>{str(item.get("wallet", "")).title()}</strong></span>
          </div>

          <p class="submission-status-text">
            <strong>Bank:</strong> {item.get("bank_name", "")}<br>
            <strong>Account Number:</strong> {item.get("account_number", "")}<br>
            <strong>Account Name:</strong> {item.get("account_name", "")}<br>
            <strong>Email:</strong> {item.get("email", "")}
          </p>

          {buttons}
        </article>
        """)

    if not cards:
        cards.append(
            '<div class="empty-tasks">No withdrawal requests yet.</div>'
        )

    page = page.replace(
        "{{WITHDRAWAL_CARDS}}",
        "\n".join(cards)
    )

    return page


@app.route("/admin/withdrawal/<request_id>/<action>", methods=["POST"])
def admin_withdrawal_action(request_id, action):
    if not session.get("admin"):
        return redirect("/admin-login.html")

    if action not in ("approve", "reject"):
        return "Invalid action.", 400

    withdrawals = load_withdrawals()

    target = next(
        (
            item for item in withdrawals
            if str(item.get("id")) == str(request_id)
        ),
        None
    )

    if not target:
        return "Withdrawal request not found.", 404

    if target.get("status") != "Pending":
        return "This withdrawal has already been reviewed.", 400

    if action == "reject":
        target["status"] = "Rejected"
        save_withdrawals(withdrawals)
        return redirect("/admin-withdrawals.html")

    users = load_users()

    stored_user = next(
        (
            u for u in users
            if str(u.get("id")) == str(target.get("user_id"))
        ),
        None
    )

    if not stored_user:
        return "User account not found.", 404

    wallet_key = (
        "task_wallet"
        if target.get("wallet") == "task"
        else "referral_wallet"
    )

    balance = float(stored_user.get(wallet_key, 0) or 0)
    amount = float(target.get("amount", 0) or 0)

    if balance < amount:
        return (
            "User does not have enough wallet balance "
            "to approve this withdrawal."
        ), 400

    stored_user[wallet_key] = round(balance - amount, 2)
    target["status"] = "Approved"

    save_users(users)
    save_withdrawals(withdrawals)

    return redirect("/admin-withdrawals.html")



if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )
