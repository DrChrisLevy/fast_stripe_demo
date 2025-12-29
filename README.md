# Fast Stripe Demo

A **passwordless e-commerce storefront** demo built with [FastHTML](https://fastht.ml/), [FastStripe](https://github.com/AnswerDotAI/faststripe), and [FastLite](https://github.com/AnswerDotAI/fastlite).

[FastStripe](https://github.com/AnswerDotAI/faststripe) is a Python library by [Answer.ai](https://answer.ai/) that simplifies Stripe integration. See their [blog post](https://www.answer.ai/posts/2025-07-23-faststripe.html) for details. For a minimal example, check out the [FastHTML e-commerce example](https://github.com/AnswerDotAI/fasthtml-example/tree/main/e_commerce).

**How it works:**
1. Guest clicks "Buy Now" → redirected to Stripe Checkout
2. After payment, user record is created and a magic login link is emailed
3. User is auto-logged in and can access purchased content
4. Future logins via magic link (no passwords)

See [tutorial.md](tutorial.md) for a detailed code walkthrough.

## Environment Files

- **`.env`** — Local development (not committed to git)
- **`plash.env`** — Production deployment on [Plash](https://pla.sh/) (not committed to git)

## Setup (Local Dev)

1. Create an account at [Stripe](https://stripe.com/) and get your **Secret key** (`sk_test_...`) from [Stripe Dashboard → API keys](https://dashboard.stripe.com/test/apikeys)
   - Only need Secret key (server-side) — not Publishable key

2. [Install Stripe CLI](https://docs.stripe.com/stripe-cli/install) & login:
   ```bash
   brew install stripe/stripe-cli/stripe  # macOS
   stripe login
   ```

3. Forward webhooks to localhost (keep running in separate terminal):
   ```bash
   stripe listen --forward-to localhost:5001/webhook
   ```
   CLI will output: `Ready! Your webhook signing secret is whsec_xxxxx`
   This will be your `STRIPE_WEBHOOK_SECRET` for local development.

4. Add to `.env`:
   ```
   STRIPE_SECRET_KEY=sk_test_...
   STRIPE_WEBHOOK_SECRET=whsec_xxxxx
   FAST_APP_SECRET=<random-string>
   ```
   For example, can generate `FAST_APP_SECRET` with: `python -c "import secrets; print(secrets.token_urlsafe(32))"`. This is used to cryptographically sign the cookie used by the session.

5. Install dependencies and run:
   ```bash
   uv sync
   uv run python main.py
   ```

## Email Setup (Resend)

Magic login links are sent via [Resend](https://resend.com).

**Skip email setup:** If you just want to test locally, edit `send_login_email()` in `main.py` to print the URL instead:
```python
def send_login_email(to, token):
    print(f"Login link for {to}: {BASE_URL}/login/{token}")
```

**To enable real emails:**

1. Sign up at [resend.com](https://resend.com) and get your API key

2. Add your domain in Resend dashboard → **Domains** → **Add Domain**

3. Add the DNS records Resend provides to your domain registrar (Cloudflare, etc.):
   - Usually 2-3 TXT records for verification
   - Wait a few minutes, then click "Verify" in Resend

4. Add to `.env` (local dev):
   ```
   RESEND_API_KEY=re_xxxxx
   EMAIL_FROM=onboarding@resend.dev
   ```
   `onboarding@resend.dev` is a test FROM address so you can send emails before verifying your own domain. Emails still go to real recipients.

## Deploy to Plash (`plash.env`)

1. Add your Stripe **Secret key** to `plash.env`.

2. Create a webhook endpoint in [Stripe Dashboard → Webhooks](https://dashboard.stripe.com/webhooks):
   - Click **Add endpoint**
   - URL: `https://yourdomain.com/webhook`
   - Select event: `checkout.session.completed`
   - After creating, click the endpoint → **Reveal** signing secret to get `whsec_...`

3. Add to `plash.env`:
   ```
   STRIPE_SECRET_KEY=sk_live_...
   STRIPE_WEBHOOK_SECRET=whsec_...
   FAST_APP_SECRET=<random-string>
   RESEND_API_KEY=re_xxxxx
   EMAIL_FROM=login@yourdomain.com
   BASE_URL=https://yourdomain.com
   ```

## Deployment (Plash)

1. Export dependencies:
   ```bash
   uv export --no-hashes --no-dev -o requirements.txt
   ```

2. Deploy:
   ```bash
   uv run plash_deploy
   ```

## Test Payment

Use test card: `4242 4242 4242 4242` with any future expiry and CVC.
