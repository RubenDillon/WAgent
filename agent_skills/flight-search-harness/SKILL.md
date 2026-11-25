---
name: flight-search-harness
description: autonomous flight-booking-form discovery and repair workflow for browser agents. Use when learning or repairing how to search a new airline, OTA, or travel provider; locating origin, destination, dates, passengers, cabin, currency, and flight-search controls; handling autocomplete, calendars, overlays, site-search traps, and validating USD flight results.
---
# Flight Search Harness

Treat flight search as a controlled state machine, not free-form browsing.

## Workflow

1. Locate a flight-booking form. Reject help/site search.
2. Complete roles in order: trip type, origin, destination, departure, return, adults, cabin, currency.
3. Prefer a provider's native USD option. Convert only when USD is unavailable.
4. Submit only after validating all roles.
5. Validate result route, dates, passenger count, cabin, currency, and total price.
6. Produce a candidate procedure. Never promote it until shadow validation succeeds.

Read `references/form-semantics.md` when identifying controls.
Read `references/navigation-patterns.md` when handling autocomplete, calendars, overlays, or loops.
Read `references/validation-rules.md` before declaring success or extracting a price.
Read `references/aerolineas-lessons.md` when repairing an airline UI or when React state differs from visible text.

## State machine

Use exactly these states:

`LOCATE_FORM → SET_TRIP_TYPE → SET_ORIGIN → SET_DESTINATION → SET_DEPARTURE → SET_RETURN → SET_PASSENGERS → SET_CABIN → SET_CURRENCY → SUBMIT → VALIDATE_RESULTS → EXTRACT_TOTAL → COMPLETE`

Do not skip a state unless the provider clearly prefilled it and Python validation confirms it.

## Action policy

- Prefer semantic controls and high-level tools over raw clicking.
- Never type a whole itinerary into a general site-search field.
- For airport autocomplete, type the IATA code and confirm a suggestion containing the exact IATA code.
- If a modal blocks interaction, resolve the topmost modal before continuing.
- If three actions make no semantic progress, use `back` or `restart` and choose a different strategy.
- Never enter identity, document, loyalty-account, or payment data.
- Never solve or bypass CAPTCHA.
- Never infer a price from promotions, installments, baggage, seats, or “from” prices.

## Output contract

Return one action JSON object only:

```json
{"action":"fill","target_id":12,"value":"EZE","reason":"origin control"}
```

Allowed actions: `click`, `fill`, `select`, `press`, `fill_airport` (origin/destination, with `iata`), `fill_date` (departure/return, with ISO `iso`), `wait`, `back`, `restart`, `fail`.
The `target_id` must be an integer copied from the current observation.
For `fill` and `select`, `value` is mandatory and non-empty.
Do NOT emit `finish`: Python validators decide completion (route, dates, passengers, currency, total price). The LLM never supplies the price.
