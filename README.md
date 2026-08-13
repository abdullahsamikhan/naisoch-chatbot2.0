# naisoch.com.pk storefront chatbot

Single-store FastAPI backend + vanilla JS widget. Answers customer questions
about products, availability, and store policies using live Shopify catalog
data + Gemini function calling. No Postgres, no Redis, no vector DB - a flat
SQLite + numpy cache on a Railway persistent volume.

## What's in here

```
app/
  main.py               FastAPI app, CORS, rate-limit wiring
  config.py             env-driven Settings
  db.py                 sqlite helpers (token store + catalog metadata)
  security.py           constant-time admin secret check
  shopify/
    token_manager.py    Client Credentials Grant + auto-refresh
    graphql_client.py   Admin GraphQL client (401 -> forced refresh -> retry)
    singleton.py         shared ShopifyTokenManager instance
  catalog/
    queries.py           GraphQL queries
    sync.py               pulls catalog -> embeds -> writes npy + sqlite
    search.py             query-time cosine similarity search
  chat/
    tools.py               search_products / get_product_details / get_store_policy
    service.py             Gemini function-calling orchestration
  policies/
    policies.json          static store policy content - EDIT THIS before launch
  api/
    routes_chat.py         POST /chat (rate-limited)
    routes_admin.py        POST /admin/sync (secret-header protected)
    routes_health.py        GET /health
widget/
  chat-widget.js          drop-in storefront widget, no dependencies
railway.json
requirements.txt
.env.example
```

## Prerequisites (manual, one-time)

1. **Create the app in the Shopify Dev Dashboard** (dev.shopify.com/dashboard),
   *not* the old store-admin "Develop apps" panel - that flow stopped
   accepting new apps on Jan 1, 2026. Grant scopes `read_products` and
   `read_inventory` only (add `read_orders` later if order-status lookup
   becomes a real feature). You'll get a **Client ID** and **Client Secret** -
   no token is shown anywhere; the app exchanges these for a token at runtime.
2. **Get a Gemini API key** from Google AI Studio.
3. **Fill in `app/policies/policies.json`** with naisoch's real shipping,
   returns, payment, sizing, and contact info. It ships with placeholder text
   - the bot will parrot the placeholders if you deploy without editing this.
4. **Generate an admin secret**: `openssl rand -hex 32`. This protects
   `/admin/sync` from being triggered by randoms.

## Local development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in the values from the prerequisites above
uvicorn app.main:app --reload
```

Then:
```bash
curl -X POST localhost:8000/admin/sync -H "X-Admin-Secret: <your secret>"
curl -X POST localhost:8000/chat -H "Content-Type: application/json" \
  -d '{"message": "Do you have any black hoodies?"}'
```

## Deploying to Railway

1. Push this repo to GitHub, connect the repo in Railway (enables
   push-to-deploy on every commit to main).
2. **Attach a Railway persistent volume** and mount it at, say, `/data`. Set
   `DATA_DIR=/data` in Railway's environment variables. Skipping this means
   the SQLite token store and embedding cache reset on every redeploy - full
   re-sync, wasted Gemini embedding calls, more frequent Shopify
   re-authentication than necessary.
3. Set all env vars from `.env.example` in Railway's dashboard (never commit
   `.env`).
4. Railway auto-detects the Python app via Nixpacks; `railway.json` sets the
   start command. No Dockerfile needed.

## Keeping the catalog in sync

There's deliberately no in-process scheduler (APScheduler etc. resets on
every redeploy, and push-to-deploy means frequent redeploys - a periodic job
can silently get skipped around deploy times). Instead, trigger
`POST /admin/sync` externally on a schedule:

- **Railway's own cron service** hitting the endpoint, or
- **A scheduled GitHub Actions workflow**:
  ```yaml
  on:
    schedule:
      - cron: "0 */4 * * *"   # every 4 hours - tune to how often naisoch updates stock
  jobs:
    sync:
      runs-on: ubuntu-latest
      steps:
        - run: |
            curl -X POST https://your-app.up.railway.app/admin/sync \
              -H "X-Admin-Secret: ${{ secrets.ADMIN_SYNC_SECRET }}"
  ```

Pick the interval based on how often naisoch's stock/prices actually change -
every 1-6 hours is the range suggested in the spec; product *price and stock*
shown to customers is always re-fetched live via `get_product_details` at
chat time regardless of sync freshness, so a stale sync only affects which
products show up in *search results*, not the numbers quoted.

## Adding the widget to the storefront

1. Upload `widget/chat-widget.js` to the theme's `assets/` folder (Shopify
   admin -> Online Store -> Themes -> Edit code -> Assets -> Add a new asset).
2. In `theme.liquid`, just before `</body>`:
   ```liquid
   <script src="{{ 'chat-widget.js' | asset_url }}" defer
           data-api-url="https://your-app.up.railway.app/chat"></script>
   ```

## Known gaps / things to decide before real launch

- **Policy content is placeholder** - see `app/policies/policies.json`.
- **No conversation persistence** - the widget holds history client-side and
  resends it every turn (stateless server, per the no-DB cost constraint).
  This means a page refresh loses chat history and Gemini re-processes the
  full transcript every turn - fine for a typical short shopping chat, but if
  conversations run very long this both gets slower and costs more per turn
  since the whole history is resent as input tokens each time.
- **Single Railway instance assumed.** `slowapi`'s rate limiting is
  per-process and in-memory; if you ever scale to 2+ instances, per-IP limits
  become per-instance rather than global (not wrong, just weaker than it
  looks). Same caveat applies to the in-memory token cache layer, though the
  sqlite-backed persistence underneath means correctness isn't affected,
  only cache-hit efficiency.
- **Embedding cache staleness window** = your sync interval. If naisoch
  publishes a brand-new product, it won't show up in `search_products`
  until the next sync runs (or you trigger one manually). Existing products'
  price/stock are always fetched live regardless.
- **Confirm the Gemini model name is still current** before going live -
  `gemini-2.5-flash-lite` is set as the default in `.env.example`, but Google
  renames/rotates the cheapest Flash-Lite tier every few months. Check
  https://ai.google.dev/gemini-api/docs/pricing before launch.
- **Multi-tenant path, if/when you build the SaaS version**: `ShopifyTokenManager.get_valid_token()`
  already accepts a `shop` parameter so it isn't hardcoded to naisoch, but
  auth itself is a different flow for third-party merchants (Authorization
  Code Grant / Token Exchange, per-merchant offline tokens, a Partner
  Dashboard app instead of a Dev Dashboard client) - budget for that as a
  real milestone, not a config change.
