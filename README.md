# Cards Project

Backend for a deterministic travel credit-card optimizer. The goal is to help employees choose the best card and vendor for flights and hotels by minimizing effective cost while still showing the full best-to-worst ranking for qualitative decisions.

This backend does not use machine learning. It uses explicit math rules taken from the `Cards Project.xlsx` workbook.

## Current Scope

- Backend only.
- Ranks all eligible card/vendor options from best to worst.
- Also returns a best-to-worst card ranking so employees can choose based on qualitative factors.
- Records whether the employee accepted or declined the recommendation.
- Requires a reason when the employee declines.
- Does not write transaction history when a recommendation is generated.
- Does not write transaction history when a decision is recorded.
- Writes the monthly audit transaction log only after the employee submits the final amount paid.
- Uses finalized historical transactions to reduce future daily/monthly/statement-cycle cap availability.

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
        audit_ledger.py         # JSONL decision and transaction logs
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
    main.py                     # FastAPI app factory
  tests/
    test_recommendation_engine.py
  requirements.txt
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
- Runtime logs are written under `backend/data/runtime/` and should not be committed.
