# Fast Stripe Demo

## Setup

1. Get your **Secret key** (`sk_test_...`) from [Stripe Dashboard → API keys](https://dashboard.stripe.com/test/apikeys)
   - Only need Secret key (server-side) — not Publishable key (that's for client-side JS)

2. Add to `plash.env`:
   ```
   STRIPE_SECRET_KEY=sk_test_...
   STRIPE_WEBHOOK_SECRET=whsec_...
   ```

3. [Install Stripe CLI](https://docs.stripe.com/stripe-cli/install) & login:
   ```bash
   brew install stripe/stripe-cli/stripe  # macOS
   stripe login
   ```

4. Forward webhooks to localhost (keep running in separate terminal):
   ```bash
   stripe listen --forward-to localhost:5001/webhook
   ```
   CLI will output: `Ready! Your webhook signing secret is whsec_xxxxx`
   
   Copy that value to `plash.env`:
   ```
   STRIPE_WEBHOOK_SECRET=whsec_xxxxx
   ```

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

4. Add to `plash.env`:
   ```
   RESEND_API_KEY=re_xxxxx
   EMAIL_FROM=login@yourdomain.com
   ```

**For local testing**: You can use Resend's test address `onboarding@resend.dev` which only delivers to your Resend account email.

## Test Payment

Use test card: `4242 4242 4242 4242` with any future expiry and CVC.
