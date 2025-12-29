# Fast Stripe Demo

[FastStripe](https://github.com/AnswerDotAI/faststripe) is a Python library
that offers several advantages over the official Stripe Python SDK. It was created
by the team at [Answer.ai](https://answer.ai/). You can read a good blog post about
it [here](https://www.answer.ai/posts/2025-07-23-faststripe.html).

I created this repo so I could learn some basics about
using FastStripe and how I could use it within a FastHTML app.


## Environment Files

- **`.env`** — Local development (not committed to git)
- **`plash.env`** — Production deployment on [Plash](https://pla.sh/) (not committed to git)

## Setup (Local Dev)

1. Get your **Secret key** (`sk_test_...`) from [Stripe Dashboard → API keys](https://dashboard.stripe.com/test/apikeys)
   - Only need Secret key (server-side) — not Publishable key (that's for client-side JS)

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

4. Add to `.env`:
   ```
   STRIPE_SECRET_KEY=sk_test_...
   STRIPE_WEBHOOK_SECRET=whsec_xxxxx
   FAST_APP_SECRET=<random-string>
   ```
   Generate `FAST_APP_SECRET` with: `python -c "import secrets; print(secrets.token_urlsafe(32))"`

5. Run the app:
   ```bash
   uv run python main.py
   ```

## Email Setup (Resend)

Magic login links are sent via [Resend](https://resend.com). To enable:

1. Sign up at [resend.com](https://resend.com) and get your API key

2. Add your domain in Resend dashboard → **Domains** → **Add Domain**

3. Add the DNS records Resend provides to your domain registrar (Cloudflare, Porkbun, etc.):
   - Usually 2-3 TXT records for verification
   - Wait a few minutes, then click "Verify" in Resend

4. Add to `.env` (local dev):
   ```
   RESEND_API_KEY=re_xxxxx
   EMAIL_FROM=onboarding@resend.dev
   ```
   `onboarding@resend.dev` is a test FROM address so you can send emails before verifying your own domain. Emails still go to real recipients.

## Production (`plash.env`)

1. Get your **live Secret key** (`sk_live_...`) from [Stripe Dashboard → API keys](https://dashboard.stripe.com/apikeys)

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
   Generate a different `FAST_APP_SECRET` for production.

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
