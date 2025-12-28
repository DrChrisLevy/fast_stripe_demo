# ruff: noqa: F403, F405
from fasthtml.common import *
from fastlite import database
from faststripe.core import StripeApi
import os
import stripe
import secrets
from dotenv import load_dotenv
from datetime import datetime, timedelta

load_dotenv("plash.env")

# --- CONFIG & DATABASE ---
DB_NAME = "data/data.db"
BASE_URL = os.getenv("BASE_URL", "http://0.0.0.0:5001")
PRODUCTS = {
    "p1": {"name": "Product 1", "price": 1999, "desc": "Generic description for product 1"},
    "p2": {"name": "Product 2", "price": 2999, "desc": "Generic description for product 2"},
}

db = database(DB_NAME)
users, links, buys = db.t.users, db.t.magic_links, db.t.purchases

# Auto-initialize DB tables
if users not in db.t:
    users.create(id=int, email=str, pk="id")
    users.create_index(["email"], unique=True)
if links not in db.t:
    links.create(id=int, email=str, token=str, expires=str, used=bool, pk="id")
if buys not in db.t:
    buys.create(id=int, user_id=int, prod_id=str, sess_id=str, amt=int, pk="id")


# --- AUTH LOGIC (The Gatekeeper) ---
def before(req, sess):
    print(f"DEBUG: Before middleware - Session: {sess}")
    req.scope["user_id"] = sess.get("user_id")


beforeware = Beforeware(before, skip=[r"/favicon\.ico", r"/static/.*", r".*\.css", r".*\.js", "/webhook", "/login/.*", "/request-login"])

app, rt = fast_app(
    before=beforeware,
    pico=False,
    hdrs=(
        Link(href="https://cdn.jsdelivr.net/npm/daisyui@5/daisyui.css", rel="stylesheet"),
        Link(href="https://cdn.jsdelivr.net/npm/daisyui@5/themes.css", rel="stylesheet"),
        Script(src="https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4"),
    ),
    secret_key=os.getenv("FAST_APP_SECRET"),
    max_age=365 * 24 * 3600,
    htmlkw={"data-theme": "light"},
)

sapi = StripeApi(os.getenv("STRIPE_SECRET_KEY"))
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")


# --- UI COMPONENTS ---
def card(pid, p, owned=False):
    lbl, href, btn = ("Enter →", f"/view/{pid}", "btn btn-success") if owned else ("Buy Now", f"/buy/{pid}", "btn btn-primary")
    return Div(
        H2(p["name"], cls="card-title"),
        P(p["desc"], cls="text-base-content/70"),
        Div(
            Span(f"${p['price'] / 100:.2f}", cls="text-2xl font-bold text-primary"),
            A(lbl, href=href, cls=btn),
            cls="card-actions justify-between items-center mt-4",
        ),
        cls="card bg-base-200 shadow-xl p-6 hover:shadow-2xl transition-all",
    )


# --- ROUTES ---
@rt("/")
def home(req):
    uid = req.scope.get("user_id")
    owned = [p["prod_id"] for p in buys.rows_where("user_id = ?", [uid])] if uid else []
    return Div(
        H1("Storefront", cls="text-4xl font-bold text-center mb-8 text-primary"),
        Div(*[card(pid, p, pid in owned) for pid, p in PRODUCTS.items()], cls="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8"),
        Div(
            A("Login", href="/request-login", cls="btn btn-outline") if not uid else A("Logout", href="/logout", cls="btn btn-ghost"),
            cls="text-center",
        ),
        cls="container mx-auto p-8 max-w-4xl",
    )


@rt("/buy/{pid}")
def buy(pid: str, req):
    uid = req.scope.get("user_id")
    email = next((u["email"] for u in users.rows_where("id = ?", [uid])), None) if uid else None

    p = PRODUCTS[pid]
    kwargs = {"customer_email": email} if email else {}
    chk = sapi.one_time_payment(
        p["name"],
        p["price"],
        f"{BASE_URL}/view/{pid}?session_id={{CHECKOUT_SESSION_ID}}",
        f"{BASE_URL}/",
        currency="cad",
        metadata={"pid": pid},
        **kwargs,
    )
    return RedirectResponse(chk.url)


@rt("/view/{pid}")
def view(pid: str, req, sess, session_id: str = None):
    uid = req.scope.get("user_id")

    # Auto-login if returning from a successful Stripe purchase
    if not uid and session_id:
        try:
            s = stripe.checkout.Session.retrieve(session_id)
            if s.payment_status == "paid" and s.metadata.get("pid") == pid:
                email = s.customer_details.email
                u = next(users.rows_where("email = ?", [email]), None) or users.insert(email=email)
                # Idempotent purchase recording (in case webhook hasn't run yet)
                if not next(buys.rows_where("sess_id = ?", [s.id]), None):
                    buys.insert(user_id=u["id"], prod_id=pid, sess_id=s.id, amt=s.amount_total)
                sess["user_id"] = u["id"]
                uid = u["id"]
        except Exception as e:
            print(f"DEBUG: Auto-login failed for session {session_id}: {e}")

    # Final check: is the user logged in AND do they own this product?
    if not uid or not next(buys.rows_where("user_id = ? AND prod_id = ?", [uid, pid]), None):
        return RedirectResponse("/")

    p = PRODUCTS.get(pid, {"name": "Unknown Product"})
    return Div(
        A("← Back", href="/", cls="btn btn-ghost btn-sm mb-4"),
        H1(f"Viewing: {p['name']}", cls="text-3xl font-bold mb-4"),
        Div("Premium content goes here. Only owners can see this.", cls="alert alert-success"),
        cls="container mx-auto p-8 max-w-4xl",
    )


@rt("/webhook", methods=["POST"])
async def stripe_webhook(req):
    try:
        ev = stripe.Webhook.construct_event(await req.body(), req.headers.get("stripe-signature"), os.getenv("STRIPE_WEBHOOK_SECRET"))
        if ev.type == "checkout.session.completed":
            s = ev.data.object
            if not next(buys.rows_where("sess_id = ?", [s.id]), None):
                u = next(users.rows_where("email = ?", [s.customer_details.email]), None) or users.insert(email=s.customer_details.email)
                buys.insert(user_id=u["id"], prod_id=s.metadata.pid, sess_id=s.id, amt=s.amount_total)
                token = secrets.token_urlsafe(32)
                links.insert(email=s.customer_details.email, token=token, expires=(datetime.now() + timedelta(days=1)).isoformat(), used=False)
                print(f"DEBUG: Login Link: {BASE_URL}/login/{token}")
    except Exception as e:
        print(f"DEBUG: Webhook error: {e}")
        return Response(status_code=400)
    return Response(status_code=200)


@rt("/login/{token}")
def magic_login(token: str, sess):
    link = next(links.rows_where("token = ? AND used = 0", [token]), None)
    if not link or datetime.now() > datetime.fromisoformat(link["expires"]):
        return Div(
            Div("Link Expired.", cls="alert alert-error"),
            A("← Back", href="/", cls="btn btn-ghost btn-sm mt-4"),
            cls="container mx-auto p-8 max-w-md text-center",
        )
    links.update({"id": link["id"], "used": True})
    u = next(users.rows_where("email = ?", [link["email"]]))
    sess["user_id"] = u["id"]
    return RedirectResponse("/")


@rt("/request-login", methods=["GET", "POST"])
def request_login(email: str = None):
    if email and next(users.rows_where("email = ?", [email]), None):
        tok = secrets.token_urlsafe(32)
        links.insert(email=email, token=tok, expires=(datetime.now() + timedelta(days=1)).isoformat(), used=False)
        print(f"DEBUG: Login Link: {BASE_URL}/login/{tok}")
        return Div(
            Div("Link sent! Check your email (or console).", cls="alert alert-info"),
            A("← Back", href="/", cls="btn btn-ghost btn-sm mt-4"),
            cls="container mx-auto p-8 max-w-md text-center",
        )
    return Div(
        H2("Login", cls="text-2xl font-bold mb-4"),
        Form(
            Input(name="email", placeholder="Email", type="email", cls="input input-bordered w-full max-w-xs"),
            Button("Send Link", cls="btn btn-primary ml-2"),
            method="post",
            cls="flex items-center gap-2",
        ),
        cls="container mx-auto p-8 max-w-md",
    )


@rt("/logout")
def logout(sess):
    sess.pop("user_id", None)
    return RedirectResponse("/")


serve()
