# Lessons learned from Aerolíneas Argentinas

- Autocomplete text can appear valid while React state remains uncommitted.
- Confirm airport selection with the actual suggestion and validate again after blur.
- Flexible-date switches may be enabled by default and must be disabled for exact monitoring.
- DayPicker can intercept the Search flights button. Resolve the picker first; do not blindly force-click.
- Network activity from catalogs, suggestion APIs, or searchbox rules is not proof of a flight shopping request.
- A route result can be in ARS, but the site may provide a native “Pago en USD” option. Prefer native USD.
- Never use the smallest visible ARS amount. It may be baggage, a seat, installment, or promotion.
- Validate `Total`, `Tarifa final`, or equivalent context before accepting a price.
