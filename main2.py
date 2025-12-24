# ruff: noqa: F403, F405
from fasthtml.common import *
from fastlite import database
from faststripe.core import StripeApi
import os, stripe, secrets
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
if users not in db.t: users.create(id=int, email=str, pk="id"); users.create_index(["email"], unique=True)
if links not in db.t: links.create(id=int, email=str, token=str, expires=str, used=bool, pk="id")
if buys not in db.t:  buys.create(id=int, user_id=int, prod_id=str, sess_id=str, amt=int, pk="id")

# --- AUTH LOGIC (The Gatekeeper) ---
def before(req, sess):
    print(f"DEBUG: Before middleware - Session: {sess}")
    req.scope['user_id'] = sess.get('user_id')

beforeware = Beforeware(before, skip=[r'/favicon\.ico', r'/static/.*', r'.*\.css', r'.*\.js', '/webhook', '/login/.*', '/request-login'])

app, rt = fast_app(before=beforeware, hdrs=(Link(href="https://cdn.jsdelivr.net/npm/daisyui@5", rel="stylesheet"), Script(src="https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4")), 
                   secret_key=os.getenv("FAST_APP_SECRET"), max_age=365*24*3600)

sapi = StripeApi(os.getenv("STRIPE_SECRET_KEY"))
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

# --- UI COMPONENTS ---
def card(pid, p, owned=False):
    lbl, href, cls = ("Enter", f"/view/{pid}", "btn-secondary") if owned else ("Buy", f"/buy/{pid}", "btn-primary")
    return Div(H2(p['name'], cls="card-title"), P(p['desc']), 
               Div(P(f"${p['price']/100:.2f}"), A(lbl, href=href, cls=f"btn {cls} w-full"), cls="card-actions justify-end mt-auto"),
               cls="card bg-base-100 shadow-xl p-6 h-full")

# --- ROUTES ---
@rt("/")
def get(req):
    uid = req.scope.get("user_id")
    owned = [p['prod_id'] for p in buys.rows_where("user_id = ?", [uid])] if uid else []
    return Container(
        H1("Storefront", cls="text-center text-4xl font-bold my-8"),
        Grid(*[card(pid, p, pid in owned) for pid, p in PRODUCTS.items()]),
        Hr(cls="my-12"),
        Div(A("Login", href="/request-login", cls="link") if not uid else A("Logout", href="/logout", cls="link"), cls="text-center")
    )

@rt("/buy/{pid}")
def get(pid: str, req):
    uid = req.scope.get("user_id")
    email = next((u['email'] for u in users.rows_where("id = ?", [uid])), None) if uid else None
    
    p = PRODUCTS[pid]
    kwargs = {"customer_email": email} if email else {}
    chk = sapi.one_time_payment(
        p['name'], p['price'], 
        f"{BASE_URL}/view/{pid}?session_id={{CHECKOUT_SESSION_ID}}", 
        f"{BASE_URL}/", 
        currency="cad", 
        metadata={"pid": pid},
        **kwargs
    )
    return RedirectResponse(chk.url)

@rt("/view/{pid}")
def get(pid: str, req, sess, session_id: str = None):
    uid = req.scope.get("user_id")
    
    # Auto-login if returning from a successful Stripe purchase
    if not uid and session_id:
        try:
            s = stripe.checkout.Session.retrieve(session_id)
            if s.payment_status == 'paid' and s.metadata.get('pid') == pid:
                email = s.customer_details.email
                u = next(users.rows_where("email = ?", [email]), None) or users.insert(email=email)
                # Idempotent purchase recording (in case webhook hasn't run yet)
                if not next(buys.rows_where("sess_id = ?", [s.id]), None):
                    buys.insert(user_id=u['id'], prod_id=pid, sess_id=s.id, amt=s.amount_total)
                sess['user_id'] = u['id']
                uid = u['id']
        except Exception as e:
            print(f"DEBUG: Auto-login failed for session {session_id}: {e}")

    # Final check: is the user logged in AND do they own this product?
    if not uid or not next(buys.rows_where("user_id = ? AND prod_id = ?", [uid, pid]), None):
        return RedirectResponse("/")
        
    p = PRODUCTS.get(pid, {"name": "Unknown Product"})
    return Container(
        A("← Back", href="/", cls="btn btn-ghost mb-4"),
        H1(f"Viewing: {p['name']}", cls="text-3xl font-bold"),
        Div("Premium content goes here. Only owners can see this.", cls="p-12 bg-base-200 rounded-xl mt-6 border-2 border-primary/20 shadow-inner")
    )

@rt("/webhook", methods=["POST"])
async def post(req):
    try:
        ev = stripe.Webhook.construct_event(await req.body(), req.headers.get("stripe-signature"), os.getenv("STRIPE_WEBHOOK_SECRET"))
        if ev.type == "checkout.session.completed":
            s = ev.data.object
            if not next(buys.rows_where("sess_id = ?", [s.id]), None):
                u = next(users.rows_where("email = ?", [s.customer_details.email]), None) or users.insert(email=s.customer_details.email)
                buys.insert(user_id=u['id'], prod_id=s.metadata.pid, sess_id=s.id, amt=s.amount_total)
                token = secrets.token_urlsafe(32)
                links.insert(email=s.customer_details.email, token=token, expires=(datetime.now()+timedelta(days=1)).isoformat(), used=False)
                print(f"DEBUG: Login Link: {BASE_URL}/login/{token}")
    except: return Response(status_code=400)
    return Response(status_code=200)

@rt("/login/{token}")
def get(token: str, sess):
    l = next(links.rows_where("token = ? AND used = 0", [token]), None)
    if not l or datetime.now() > datetime.fromisoformat(l['expires']): return "Link Expired."
    links.update({'id': l['id'], 'used': True})
    u = next(users.rows_where("email = ?", [l['email']]))
    sess['user_id'] = u['id']
    return RedirectResponse("/")

@rt("/request-login", methods=["GET", "POST"])
def login(email: str = None):
    if email and (u := next(users.rows_where("email = ?", [email]), None)):
        tok = secrets.token_urlsafe(32)
        links.insert(email=email, token=tok, expires=(datetime.now()+timedelta(days=1)).isoformat(), used=False)
        print(f"DEBUG: Login Link: {BASE_URL}/login/{tok}")
        return P("Link sent! Check your email (or console).")
    return Container(H2("Login"), Form(Input(name="email", placeholder="Email", type="email"), Button("Send Link"), method="post"))

@rt("/logout")
def get(sess): sess.pop('user_id', None); return RedirectResponse("/")

serve()