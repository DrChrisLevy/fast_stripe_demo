# FastHTML + Stripe Integration Tutorial

A comprehensive guide to understanding this passwordless e-commerce application built with FastHTML, FastLite, and Stripe.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Dependencies & Imports](#dependencies--imports)
3. [Configuration & Database Setup](#configuration--database-setup)
4. [Authentication System](#authentication-system)
5. [User Creation & Session Management](#user-creation--session-management)
6. [Stripe Integration Deep Dive](#stripe-integration-deep-dive)
7. [Routes Explained](#routes-explained)
8. [The Complete Purchase Flow](#the-complete-purchase-flow)
9. [Security Considerations](#security-considerations)

---

## Architecture Overview

This application is a **passwordless e-commerce storefront** with three main components:

```
┌─────────────────────────────────────────────────────────────────┐
│                        User Browser                              │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     FastHTML Application                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │ Beforeware  │  │   Routes    │  │    Stripe Integration   │  │
│  │ (Auth Gate) │  │ (Handlers)  │  │  (Payments & Webhooks)  │  │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
┌─────────────────────────┐     ┌─────────────────────────┐
│    SQLite Database      │     │     Stripe API          │
│  (users, links, buys)   │     │  (Checkout, Webhooks)   │
└─────────────────────────┘     └─────────────────────────┘
```

**Key Concepts:**
- **Passwordless Auth**: Users log in via magic links (emailed tokens), no passwords stored
- **Session-Based State**: User identity stored in encrypted session cookies
- **Idempotent Purchases**: Purchases are recorded safely even if webhooks/redirects race

---

## Dependencies & Imports

```python
# ruff: noqa: F403, F405
from fasthtml.common import *          # FastHTML framework (star import)
from fastlite import database          # Lightweight SQLite ORM
from faststripe.core import StripeApi  # Stripe helper library
import os, stripe, secrets             # Standard lib + Stripe SDK
from dotenv import load_dotenv         # Environment variable loading
from datetime import datetime, timedelta
```

### What Each Library Does:

| Library | Purpose |
|---------|---------|
| `fasthtml` | Web framework (like Flask/FastAPI but simpler) |
| `fastlite` | SQLite database with dict-like access |
| `faststripe` | Wrapper around Stripe for common operations |
| `stripe` | Official Stripe Python SDK |
| `secrets` | Cryptographically secure token generation |
| `dotenv` | Load `.env` files into environment |

The `# ruff: noqa: F403, F405` comment tells the linter to ignore warnings about star imports.

---

## Configuration & Database Setup

### Environment Variables

```python
load_dotenv("plash.env")
```

This loads your `plash.env` file. You need these variables:

```env
BASE_URL=http://0.0.0.0:5001        # Your app's public URL
STRIPE_SECRET_KEY=sk_test_...       # Stripe secret key
STRIPE_WEBHOOK_SECRET=whsec_...     # Webhook signing secret
FAST_APP_SECRET=your-secret-here    # Session encryption key
```

### Product Catalog

```python
PRODUCTS = {
    "p1": {"name": "Product 1", "price": 1999, "desc": "Generic description for product 1"},
    "p2": {"name": "Product 2", "price": 2999, "desc": "Generic description for product 2"},
}
```

**Important**: Prices are in **cents** (1999 = $19.99). This is Stripe's convention to avoid floating-point issues.

### Database Schema

```python
db = database(DB_NAME)
users, links, buys = db.t.users, db.t.magic_links, db.t.purchases
```

`db.t.tablename` is FastLite's way of accessing tables. The tables are created if they don't exist:

```python
# Users table - stores registered users
if users not in db.t:
    users.create(id=int, email=str, pk="id")
    users.create_index(["email"], unique=True)  # Prevent duplicate emails

# Magic links table - for passwordless login
if links not in db.t:
    links.create(id=int, email=str, token=str, expires=str, used=bool, pk="id")

# Purchases table - records of completed purchases
if buys not in db.t:
    buys.create(id=int, user_id=int, prod_id=str, sess_id=str, amt=int, pk="id")
```

**Schema Diagram:**

```
┌──────────────┐     ┌──────────────────┐     ┌──────────────────┐
│    users     │     │   magic_links    │     │    purchases     │
├──────────────┤     ├──────────────────┤     ├──────────────────┤
│ id (PK)      │◄────│ email            │     │ id (PK)          │
│ email (UQ)   │     │ token            │     │ user_id (FK)     │──►users.id
└──────────────┘     │ expires          │     │ prod_id          │
                     │ used             │     │ sess_id (UQ)     │
                     └──────────────────┘     │ amt              │
                                              └──────────────────┘
```

---

## Authentication System

### The Beforeware (Middleware)

```python
def before(req, sess):
    print(f"DEBUG: Before middleware - Session: {sess}")
    req.scope['user_id'] = sess.get('user_id')
```

This runs **before every request**. It:
1. Reads `user_id` from the encrypted session cookie
2. Attaches it to `req.scope` for easy access in route handlers

```python
beforeware = Beforeware(
    before,
    skip=[
        r'/favicon\.ico',
        r'/static/.*',
        r'.*\.css',
        r'.*\.js',
        '/webhook',           # Webhooks can't have sessions
        '/login/.*',          # Login links must work without auth
        '/request-login'      # Login form must be accessible
    ]
)
```

The `skip` list defines routes that bypass the middleware. Regex patterns are supported.

### App Initialization

```python
app, rt = fast_app(
    before=beforeware,
    pico=False,                    # Don't use PicoCSS
    hdrs=(                         # Custom CSS/JS headers
        Link(href="https://cdn.jsdelivr.net/npm/daisyui@5/daisyui.css", rel="stylesheet"),
        Link(href="https://cdn.jsdelivr.net/npm/daisyui@5/themes.css", rel="stylesheet"),
        Script(src="https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4"),
    ),
    secret_key=os.getenv("FAST_APP_SECRET"),  # Session encryption
    max_age=365*24*3600,                       # Cookie lasts 1 year
    htmlkw={"data-theme": "light"}             # DaisyUI theme
)
```

**Key Points:**
- `secret_key` encrypts the session cookie (users can't tamper with it)
- `max_age` keeps users logged in for a year
- `rt` is the route decorator (shorthand for `app.route`)

---

## User Creation & Session Management

Understanding **when** users are created and **when** they get logged in is crucial to understanding this app.

### When is a User Record Created?

Users are **only created when they purchase something**. There's no separate "sign up" flow.

A user record is created in **two places** (whichever runs first):

**1. The Webhook Handler** (`main.py:117`):
```python
u = next(users.rows_where("email = ?", [s.customer_details.email]), None) \
    or users.insert(email=s.customer_details.email)
#        ↑ Creates user if they don't exist
```

**2. The Redirect Handler** (`main.py:89`):
```python
u = next(users.rows_where("email = ?", [email]), None) \
    or users.insert(email=email)
#        ↑ Creates user if they don't exist
```

Both use the same pattern: "get existing user OR create new one". This is safe because of the unique email index on the users table.

### When is the Session `user_id` Set?

The session cookie gets the `user_id` (logging the user in) in **two places**:

**1. Auto-login after purchase** (`main.py:93`):
```python
sess['user_id'] = u['id']  # Right after Stripe redirect
```

**2. Magic link login** (`main.py:131`):
```python
sess['user_id'] = u['id']  # When clicking login link
```

### The Complete User Lifecycle

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         USER LIFECYCLE DIAGRAM                               │
└─────────────────────────────────────────────────────────────────────────────┘

Guest visits site (no user record, no session)
        │
        ▼
Clicks "Buy Now" ──► Redirected to Stripe
        │
        ▼
Completes Stripe payment (enters email on Stripe's form)
        │
        │
        ├───────────────────────────────────┐
        │                                   │
        ▼                                   ▼
   /view/{pid} redirect              /webhook POST
   (usually runs first)              (runs async from Stripe)
        │                                   │
        ▼                                   ▼
   ┌─────────────────┐              ┌─────────────────┐
   │ User exists?    │              │ User exists?    │
   │   NO → Create   │              │   NO → Create   │
   │   YES → Fetch   │              │   YES → Fetch   │
   └─────────────────┘              └─────────────────┘
        │                                   │
        ▼                                   ▼
   sess['user_id'] = u['id']        Generate magic link
   (USER IS NOW LOGGED IN)          (for future logins)
        │
        ▼
   User sees purchased content
        │
        ▼
   ... time passes, session expires or user logs out ...
        │
        ▼
   User clicks magic link from email (or requests new one)
        │
        ▼
   /login/{token} ──► sess['user_id'] = u['id']
   (USER IS LOGGED IN AGAIN)
```

### Why Can't Users "Sign Up" Without Buying?

The `/request-login` route (`main.py:136`) explicitly checks if the user **already exists**:

```python
if email and (u := next(users.rows_where("email = ?", [email]), None)):
    # Only creates magic link if user exists
    tok = secrets.token_urlsafe(32)
    links.insert(...)
```

If the email isn't in the database, nothing happens. This is intentional - it's a **purchase-gated** system where the only way to become a user is to buy something.

### The Two Types of `user_id`

Don't confuse these:

| Name | What It Is | Where It Lives |
|------|-----------|----------------|
| `u['id']` | Database primary key | `users` table |
| `sess['user_id']` | Session variable | Encrypted cookie |

The flow is: Database `id` → copied into → Session `user_id` → read by → Beforeware → attached to → `req.scope['user_id']`

```python
# Beforeware reads from session, attaches to request
def before(req, sess):
    req.scope['user_id'] = sess.get('user_id')

# Routes read from request scope
@rt("/")
def get(req):
    uid = req.scope.get("user_id")  # This is the database ID
```

---

## Stripe Integration Deep Dive

### Stripe Client Setup

```python
sapi = StripeApi(os.getenv("STRIPE_SECRET_KEY"))  # faststripe helper
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")   # official SDK
```

Two clients are initialized:
1. `sapi` - The `faststripe` wrapper for simplified checkout creation
2. `stripe` - The official SDK for webhooks and session retrieval

### Creating a Checkout Session

```python
@rt("/buy/{pid}")
def get(pid: str, req):
    uid = req.scope.get("user_id")
    email = next((u['email'] for u in users.rows_where("id = ?", [uid])), None) if uid else None

    p = PRODUCTS[pid]
    kwargs = {"customer_email": email} if email else {}

    chk = sapi.one_time_payment(
        p['name'],                                              # Product name
        p['price'],                                             # Price in cents
        f"{BASE_URL}/view/{pid}?session_id={{CHECKOUT_SESSION_ID}}",  # Success URL
        f"{BASE_URL}/",                                         # Cancel URL
        currency="cad",                                         # Currency
        metadata={"pid": pid},                                  # Custom data
        **kwargs                                                # Optional email
    )
    return RedirectResponse(chk.url)
```

**Breakdown:**

1. **Get user email if logged in** - Pre-fills checkout form
2. **Build checkout parameters**:
   - `success_url` includes `{CHECKOUT_SESSION_ID}` - Stripe replaces this with the actual session ID
   - `metadata` stores your custom data (product ID) - retrieved later in webhooks
3. **Redirect to Stripe** - User completes payment on Stripe's hosted page

**The `{CHECKOUT_SESSION_ID}` Template (URL Template Variables):**

This uses a technique called **URL template variables** (or placeholder substitution). You include a placeholder in the URL, and Stripe's server replaces it with the actual value when redirecting the user back to your site.

**The 3-step flow:**

```
STEP 1 - YOUR CODE (line 70-71):
─────────────────────────────────
f"{BASE_URL}/view/{pid}?session_id={{CHECKOUT_SESSION_ID}}"
                                   ↑↑                    ↑↑
                          Double braces in f-string = single literal braces

STEP 2 - WHAT STRIPE RECEIVES:
──────────────────────────────
"http://0.0.0.0:5001/view/p1?session_id={CHECKOUT_SESSION_ID}"
                                        ↑                    ↑
                              Literal braces with placeholder

STEP 3 - WHAT STRIPE SENDS TO USER'S BROWSER (after payment):
─────────────────────────────────────────────────────────────
"http://0.0.0.0:5001/view/p1?session_id=cs_test_a1b2c3d4e5..."
                                        ↑───────────────────↑
                              Stripe replaced it with actual session ID
```

**Key point:** You never populate this value - **Stripe's server does** during the redirect. The `{CHECKOUT_SESSION_ID}` placeholder is the only template variable Stripe supports for Checkout URLs.

### The Webhook Handler

```python
@rt("/webhook", methods=["POST"])
async def post(req):
    try:
        # Step 1: Verify the webhook is from Stripe
        ev = stripe.Webhook.construct_event(
            await req.body(),                              # Raw request body
            req.headers.get("stripe-signature"),           # Stripe's signature header
            os.getenv("STRIPE_WEBHOOK_SECRET")             # Your webhook secret
        )

        # Step 2: Handle checkout completion
        if ev.type == "checkout.session.completed":
            s = ev.data.object  # The checkout session object

            # Step 3: Idempotent insert (prevent duplicates)
            if not next(buys.rows_where("sess_id = ?", [s.id]), None):
                # Get or create user
                u = next(users.rows_where("email = ?", [s.customer_details.email]), None) \
                    or users.insert(email=s.customer_details.email)

                # Record purchase
                buys.insert(
                    user_id=u['id'],
                    prod_id=s.metadata.pid,   # From your metadata!
                    sess_id=s.id,             # Stripe session ID
                    amt=s.amount_total        # Amount paid
                )

                # Generate magic link for login
                token = secrets.token_urlsafe(32)
                links.insert(
                    email=s.customer_details.email,
                    token=token,
                    expires=(datetime.now()+timedelta(days=1)).isoformat(),
                    used=False
                )
                print(f"DEBUG: Login Link: {BASE_URL}/login/{token}")

    except:
        return Response(status_code=400)  # Tell Stripe something went wrong

    return Response(status_code=200)  # Success
```

**Critical Concepts:**

1. **Webhook Verification** (Line 113):
   ```python
   stripe.Webhook.construct_event(body, signature, secret)
   ```
   This cryptographically verifies the request came from Stripe. Without this, anyone could fake purchase events!

2. **Idempotency Check** (Line 116):
   ```python
   if not next(buys.rows_where("sess_id = ?", [s.id]), None):
   ```
   Webhooks can be delivered multiple times. This check ensures you only process each payment once by checking if `sess_id` already exists.

3. **Metadata Retrieval** (Line 118):
   ```python
   prod_id=s.metadata.pid
   ```
   The `pid` you passed during checkout is now available in the webhook!

**Webhook Flow Diagram:**

```
┌─────────────┐     ┌─────────────┐     ┌─────────────────┐
│   Stripe    │────►│ Your Server │────►│    Database     │
│  (Payment)  │     │  /webhook   │     │ (Record Purchase)│
└─────────────┘     └─────────────┘     └─────────────────┘
       │                   │
       │   POST request    │
       │   with signature  │
       │                   │
       │   ◄── 200 OK ─────│
```

### Auto-Login After Purchase

```python
@rt("/view/{pid}")
def get(pid: str, req, sess, session_id: str = None):
    uid = req.scope.get("user_id")

    # Auto-login if returning from Stripe
    if not uid and session_id:
        try:
            s = stripe.checkout.Session.retrieve(session_id)

            if s.payment_status == 'paid' and s.metadata.get('pid') == pid:
                email = s.customer_details.email

                # Get or create user
                u = next(users.rows_where("email = ?", [email]), None) \
                    or users.insert(email=email)

                # Idempotent purchase (in case webhook hasn't fired yet)
                if not next(buys.rows_where("sess_id = ?", [s.id]), None):
                    buys.insert(
                        user_id=u['id'],
                        prod_id=pid,
                        sess_id=s.id,
                        amt=s.amount_total
                    )

                # Log the user in
                sess['user_id'] = u['id']
                uid = u['id']

        except Exception as e:
            print(f"DEBUG: Auto-login failed: {e}")
```

**Why This Exists:**

There's a **race condition** between:
1. Stripe redirecting the user to your success URL
2. Stripe sending the webhook

The redirect often happens **before** the webhook arrives. This code handles that by:
1. Retrieving the session directly from Stripe API
2. Verifying payment was successful
3. Recording the purchase (if webhook hasn't yet)
4. Logging the user in immediately

**Security Checks:**
- `s.payment_status == 'paid'` - Confirms payment succeeded
- `s.metadata.get('pid') == pid` - Confirms they're accessing the right product

---

## Routes Explained

### Home Page (`/`)

```python
@rt("/")
def get(req):
    uid = req.scope.get("user_id")

    # Get list of product IDs the user owns
    owned = [p['prod_id'] for p in buys.rows_where("user_id = ?", [uid])] if uid else []

    return Div(
        H1("Storefront", cls="..."),
        Div(
            *[card(pid, p, pid in owned) for pid, p in PRODUCTS.items()],
            cls="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8"
        ),
        Div(
            A("Login", href="/request-login", cls="btn btn-outline") if not uid
            else A("Logout", href="/logout", cls="btn btn-ghost"),
            cls="text-center"
        ),
        cls="container mx-auto p-8 max-w-4xl"
    )
```

The `card()` function changes based on ownership:

```python
def card(pid, p, owned=False):
    lbl, href, btn = ("Enter →", f"/view/{pid}", "btn btn-success") if owned \
                else ("Buy Now", f"/buy/{pid}", "btn btn-primary")
    # ... renders card with appropriate button
```

### Magic Link Login

**Request a Link:**
```python
@rt("/request-login", methods=["GET", "POST"])
def login(email: str = None):
    if email and (u := next(users.rows_where("email = ?", [email]), None)):
        tok = secrets.token_urlsafe(32)  # 32 bytes = 43 characters
        links.insert(
            email=email,
            token=tok,
            expires=(datetime.now()+timedelta(days=1)).isoformat(),
            used=False
        )
        print(f"DEBUG: Login Link: {BASE_URL}/login/{tok}")
        return Div("Link sent!", ...)
    return Div(Form(...))  # Show email form
```

**Use the Link:**
```python
@rt("/login/{token}")
def get(token: str, sess):
    # Find valid, unused link
    l = next(links.rows_where("token = ? AND used = 0", [token]), None)

    # Check expiration
    if not l or datetime.now() > datetime.fromisoformat(l['expires']):
        return "Link Expired"

    # Mark as used (prevent replay attacks)
    links.update({'id': l['id'], 'used': True})

    # Log user in
    u = next(users.rows_where("email = ?", [l['email']]))
    sess['user_id'] = u['id']

    return RedirectResponse("/")
```

---

## The Complete Purchase Flow

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                           PURCHASE FLOW DIAGRAM                               │
└──────────────────────────────────────────────────────────────────────────────┘

     User                    Your App                    Stripe
       │                        │                          │
       │  1. Click "Buy Now"    │                          │
       │───────────────────────►│                          │
       │                        │                          │
       │                        │  2. Create Checkout      │
       │                        │  Session (with metadata) │
       │                        │─────────────────────────►│
       │                        │                          │
       │                        │  3. Return session URL   │
       │                        │◄─────────────────────────│
       │                        │                          │
       │  4. Redirect to Stripe │                          │
       │◄───────────────────────│                          │
       │                        │                          │
       │  5. Complete Payment   │                          │
       │──────────────────────────────────────────────────►│
       │                        │                          │
       │                        │  6. Webhook: payment     │
       │                        │     complete             │
       │                        │◄─────────────────────────│
       │                        │                          │
       │                        │  7. Record purchase,     │
       │                        │     create magic link    │
       │                        │                          │
       │  8. Redirect to        │                          │
       │     success URL        │                          │
       │◄──────────────────────────────────────────────────│
       │                        │                          │
       │  9. Auto-login &       │                          │
       │     show content       │                          │
       │◄───────────────────────│                          │
       │                        │                          │
```

**Timeline of Events:**

| Step | What Happens | Code Location |
|------|--------------|---------------|
| 1-4 | User clicks buy, redirected to Stripe | `/buy/{pid}` (lines 62-77) |
| 5 | User pays on Stripe's hosted page | Stripe handles this |
| 6-7 | Webhook records purchase | `/webhook` (lines 110-123) |
| 8 | Stripe redirects to success URL | Stripe handles this |
| 9 | Auto-login and show content | `/view/{pid}` (lines 79-108) |

---

## Security Considerations

### What's Done Well

1. **Webhook Signature Verification** - Prevents fake payment notifications
2. **Idempotent Purchase Recording** - Prevents duplicate charges
3. **Magic Link Expiration** - Links expire after 24 hours
4. **Single-Use Tokens** - Links can't be reused after login
5. **Session Encryption** - `secret_key` encrypts cookies

### Areas to Consider

1. **Magic Links in Console** - Currently printed to console. In production, send via email.

2. **Error Handling** - The bare `except:` in webhook silently catches all errors:
   ```python
   except: return Response(status_code=400)  # What went wrong?
   ```
   Consider logging the actual error.

3. **HTTPS Required** - Stripe requires HTTPS in production. The `BASE_URL` should be `https://` in production.

4. **Rate Limiting** - The `/request-login` endpoint could be abused. Consider adding rate limiting.

---

## Quick Reference

### Environment Variables Needed

```env
BASE_URL=https://yourdomain.com
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
FAST_APP_SECRET=a-long-random-string
```

### Testing Locally with Stripe CLI

```bash
# Forward webhooks to your local server
stripe listen --forward-to localhost:5001/webhook

# The CLI will give you a webhook secret to use
```

### Stripe Test Card Numbers

| Card Number | Result |
|-------------|--------|
| 4242 4242 4242 4242 | Success |
| 4000 0000 0000 0002 | Declined |
| 4000 0000 0000 3220 | 3D Secure required |

Use any future expiry date and any 3-digit CVC.

---

## Summary

This application demonstrates a clean pattern for selling digital products:

1. **No passwords** - Users authenticate via magic links
2. **Stripe handles payments** - You never touch card numbers
3. **Idempotent operations** - Safe against duplicate webhooks/requests
4. **Immediate access** - Auto-login after purchase, no waiting for webhooks

The key insight is that both the webhook AND the redirect handler can record purchases, but the `sess_id` check ensures it only happens once. This makes the system resilient to timing issues between Stripe's webhook delivery and user redirects.
