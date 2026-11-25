# Validation rules

Before success, verify:
- origin equals requested IATA;
- destination equals requested IATA;
- outbound and return dates match exactly;
- trip is round-trip;
- adult count matches;
- cabin is Economy;
- native USD is selected when offered;
- page is a flight-result context, not promotion/help/site search;
- price is a total itinerary amount with explicit currency;
- price is plausible and associated with the requested itinerary.

Reject amounts near words such as installment, monthly, baggage, seat, ancillary, tax-only, fee-only, or “from”.

If a provider cannot display USD, preserve original currency and use the single official daily BCRA USD/ARS record. Freeze that rate on the observation. Never recalculate historical observations with a later rate.
