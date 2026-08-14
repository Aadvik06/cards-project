# Cards Project

User-friendly travel credit-card optimizer for flight and hotel bookings. The backend calculates the best card/vendor option, and the frontend guides employees through the booking flow without exposing technical details.

This backend does not use machine learning. It uses explicit math rules taken from the `Cards Project.xlsx` workbook.

## Current Scope

- Backend and simple web frontend.
- Ranks all eligible card/vendor options from best to worst.
- Also returns a best-to-worst card ranking so employees can choose based on qualitative factors.
- Lets employees view past transactions and monthly/year-to-date point totals.
- Lets employees save a local draft and cancel the current booking flow.
- Separates flights, hotels, and non-travel Amex voucher tracking.
- Records whether the employee accepted or declined the recommendation.
- Requires a reason when the employee declines.
- Does not write transaction history when a recommendation is generated.
- Does not write transaction history when a decision is recorded.
- Writes the monthly audit transaction log only after the employee submits the final amount paid.
- Stores recommendations, decisions, and finalized transactions in SQLite locally or PostgreSQL in production.
- Uses finalized historical transactions from the database to reduce future daily/monthly/statement-cycle cap availability.

## Project Structure

```text
backend/
  app/
    api/
      routes/
        recommendations.py      # HTTP endpoints
      dependencies.py           # Shared service instances
    core/
      decimal_math.py           # Money and point rounding
      errors.py                 # Domain exceptions
    data/
      repositories/
        audit_ledger.py         # SQLite/PostgreSQL recommendation, decision, and transaction storage
        rules_repository.py     # Loads seed rules
      seed/
        cards.json              # Card rates, caps, point values
        vendors.json            # Approved travel vendors/platforms
        card_vendor_rules.json  # Eligible card/vendor pairs
        voucher_rules.json      # Amex voucher caps
    domain/
      recommendation_engine.py  # Ranking engine
      reward_calculator.py      # Deterministic reward math
      cap_tracker.py            # Cap remaining calculation
      models.py                 # Domain data structures
      enums.py                  # Travel and rule enums
      tie_breaker.py            # Ranking tie-break rules
    schemas/
      recommendation.py         # API request/response models
    services/
      recommendation_service.py # Recommendation and decision workflow
      transaction_service.py    # Final paid amount logging
      cap_usage_service.py      # Historical cap usage
      monthly_log_service.py    # Monthly audit log view
    static/
      index.html                # Employee booking interface
      styles.css                # Frontend styling
      app.js                    # Frontend workflow and API calls
    main.py                     # FastAPI app factory
  tests/
    test_recommendation_engine.py
  requirements.txt
render.yaml                     # Render deployment blueprint
catalyst.json                   # Zoho Catalyst AppSail project config
```

## Recommendation Math

For each eligible card/vendor quote:

```text
price_after_discount = eligible_amount * (1 - discount_rate) + cash_component
base_points = price_after_discount * card_base_rate
raw_bonus_points = (bonus_base_points * multiplier) - bonus_base_points
awarded_bonus_points = min(raw_bonus_points, remaining_daily_cap, remaining_cycle_cap)
total_points = base_points + awarded_bonus_points
points_value_rupees = total_points * point_value_rupees
net_cost = price_after_discount - points_value_rupees
```

Ranking order:

1. Lowest net cost
2. Highest total points
3. Lowest price after discount
4. Card name
5. Vendor name

## Employee Flow

The web page guides the employee through four steps:

1. Choose flight, hotel, or voucher.
2. Enter booking details and prices.
3. Review the ranked card options and choose one.
4. Enter the final amount paid at checkout.

The transaction is only logged after step 4. Voucher purchases use the same final logging step, but they skip card optimization because the purpose is only to track Amex points and cap usage.

Employees can also open the Past transactions tab to see logged transactions, current-month points, current-month bonus points, year-to-date points, and year-to-date spend.

## API Flow

### 1. Create Recommendation

`POST /recommendations`

Submit the employee, travel type, travel date, and vendor quote amounts. The response contains:

- `ranked_options`: every eligible option ranked best to worst.
- `card_rankings`: best option per card ranked best to worst.

Example:

```json
{
  "employee_id": "emp-001",
  "travel_type": "flight",
  "travel_date": "2026-08-11",
  "quotes": [
    {
      "vendor_id": "hdfc_smartbuy_flight",
      "amount": "10869",
      "discount_rate": "0"
    },
    {
      "vendor_id": "amex_mmt_flight_voucher",
      "amount": "11480",
      "discount_rate": "0"
    }
  ]
}
```

### 2. Record Employee Decision

`POST /recommendations/{recommendation_id}/decision`

Accepted:

```json
{
  "accepted": true,
  "selected_option_id": "option-id-from-response"
}
```

Declined:

```json
{
  "accepted": false,
  "selected_card_id": "amex",
  "selected_vendor_id": "amex_mmt_flight_voucher",
  "decline_reason": "Employee preferred Amex service support for this booking."
}
```

This records the decision only. It does not write the monthly transaction ledger.

### 3. Finalize Transaction

`POST /recommendations/{recommendation_id}/finalize`

Submit the final amount actually paid at checkout. This is the only step that writes the monthly audit transaction log.

```json
{
  "selected_option_id": "option-id-from-response",
  "final_amount_paid": "10999",
  "paid_at": "2026-08-11T18:30:00Z"
}
```

### 4. Monthly Audit Log

`GET /logs/monthly/{year}/{month}`

Example:

```text
GET /logs/monthly/2026/8
```

## Database

The backend supports two database modes:

- Local development: SQLite.
- Hosted production: PostgreSQL through `DATABASE_URL`.

By default, runtime data is stored here:

```text
backend/data/runtime/cards_project.sqlite3
```

If `DATABASE_URL` is set, the app uses PostgreSQL instead. This is the recommended setup for private company hosting because it is better for backups, deployments, and multi-user usage.

The database stores:

- recommendations shown to employees
- ranked recommendation options
- accepted/declined decisions
- decline reasons
- finalized paid transactions
- calculated points and net cost for audit review

Card and vendor rules are still kept in JSON seed files because they are simple configuration data right now.

## Private Hosting

Recommended production setup if using Render:

```text
Cloudflare Access
  -> Render Web Service
  -> Render PostgreSQL
```

This keeps the app available through a real URL while requiring approved users to sign in before they can open it.

### 1. Push The Repo To GitHub

Render deploys from GitHub. Push the latest repository code before deploying.

### 2. Create The Render Services

This repo includes `render.yaml`, so Render can create both services from a blueprint:

- `precisehub`: FastAPI web service.
- `precisehub-db`: managed PostgreSQL database.

In Render:

1. Create a new Blueprint.
2. Select this GitHub repository.
3. Let Render read `render.yaml`.
4. Create the services.

The web service uses:

```bash
pip install -r requirements.txt
```

Start command:

```bash
uvicorn app.main:create_app --factory --host 0.0.0.0 --port $PORT
```

Health check:

```text
/health
```

The `DATABASE_URL` environment variable is automatically connected to the managed PostgreSQL database by the blueprint.

### 3. Protect The Site With Cloudflare Access

After Render gives the app a URL, protect it before sharing it with employees.

In Cloudflare Zero Trust:

1. Go to Access controls.
2. Create an application.
3. Choose a self-hosted application.
4. Add the PreciseHub hostname, for example:

```text
precisehub.precisebiopharma.com
```

5. Add an allow policy for company users, for example:

```text
email domain equals precisebiopharma.com
```

6. Connect the hostname to the Render service.

Do not leave PreciseHub publicly open. It contains employee names, trip details, card choices, points, and transaction history.

### 4. Production Checklist

Before company use:

- Confirm HTTPS works.
- Confirm Cloudflare Access blocks non-company users.
- Confirm a test transaction saves into PostgreSQL.
- Confirm monthly history loads.
- Confirm backups are enabled for PostgreSQL.
- Keep the Render and Cloudflare admin access limited to trusted owners.

## Zoho Catalyst Hosting

Zoho Catalyst is a legitimate Zoho cloud platform. Its AppSail product supports Python web applications and lets apps read the assigned HTTP port from the `X_ZOHO_CATALYST_LISTEN_PORT` environment variable.

This repository includes Catalyst-ready files:

```text
catalyst.json
backend/app-config.json
backend/start_catalyst.py
backend/Dockerfile.catalyst
```

### Recommended Catalyst Approach

Use Catalyst AppSail for the web app, but do not rely on local SQLite for production audit data. For production, set `DATABASE_URL` to a hosted PostgreSQL database connection string.

```text
Zoho Catalyst AppSail
  -> PreciseHub FastAPI app
  -> PostgreSQL through DATABASE_URL
```

If you want all data fully inside Zoho Catalyst later, the database layer should be adapted to Catalyst Data Store. The current production-ready path is PostgreSQL because the app already supports it.

### Deploy With Catalyst Managed Python Runtime

1. Create a Zoho Catalyst project in the Catalyst console.
2. Install the Catalyst CLI:

```bash
npm install -g zcatalyst-cli@latest
```

3. Log in:

```bash
catalyst login
```

4. From the repository root, link the local project to your Catalyst project:

```bash
catalyst init
```

When prompted, select your existing Catalyst project. The repo already includes `catalyst.json`, but the CLI may update it with your account-specific project settings.

5. Confirm the AppSail service points to:

```text
backend
```

6. In Catalyst AppSail environment variables, set:

```text
DATABASE_URL=your_postgresql_connection_string
```

7. Deploy to Catalyst development:

```bash
catalyst deploy
```

8. Test the development URL.

9. Promote/deploy to production from the Catalyst console when ready.

### Catalyst Startup Command

The AppSail startup command is:

```bash
python3 -u start_catalyst.py
```

`start_catalyst.py` starts Uvicorn on the port Catalyst provides.

### Catalyst Docker Fallback

If the managed Python runtime does not install dependencies the way you need, use the Docker/custom runtime path with:

```text
backend/Dockerfile.catalyst
```

The Docker option is often cleaner for FastAPI because the image installs `requirements.txt` during the build.

## Run Locally

From the repository root:

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:create_app --factory --reload
```

Open:

```text
http://127.0.0.1:8000/
```

API docs are also available at:

```text
http://127.0.0.1:8000/docs
```

## Run Tests

From `backend/`:

```bash
python -m unittest discover -s tests
```

The tests cover:

- Workbook flight examples.
- Workbook hotel examples.
- Best-to-worst card ranking.
- Required decline reason.
- No transaction ledger write until final amount is submitted.
- Finalized historical transactions reducing future cap availability.

## Notes And Assumptions

- HDFC and Amex caps reset by calendar month.
- ICICI cap reset uses `statement_day` from seed data. It is currently set to `1` until the actual statement date is provided.
- The workbook had an inconsistency for ICICI multipliers. The seed data follows the main card table: `6x` flights and `12x` hotels.
- American Express Fine Hotels is modeled as base-points-only using a vendor-specific multiplier override of `1`.
- Runtime SQLite database files are written under `backend/data/runtime/` and should not be committed.
