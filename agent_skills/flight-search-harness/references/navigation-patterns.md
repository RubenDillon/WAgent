# Navigation patterns

## Airport autocomplete
1. Focus the role-specific field.
2. Fill only the IATA code.
3. Wait for suggestions.
4. Select a visible option containing the exact IATA code.
5. Blur and confirm the committed value. Visible text alone may not mean React state was committed.

## Date pickers
- Prefer inputs with semantic date roles.
- If a calendar is required, navigate month-by-month and select exact dates.
- Close or complete the picker before submitting.
- Do not force-click through a calendar overlay.

## Modals
- Resolve privacy, chatbot, generic search, or calendar dialogs before interacting behind them.
- Prefer explicit Close, Save, Done, Accept essential, or Cancel controls.
- Do not wait repeatedly for a persistent modal to disappear.

## Recovery
- Detect `/sitesearch`, help results, or content search and immediately go back.
- If the same semantic state is visited five times, roll back or restart.
- Preserve working providers while learning/repair runs in one isolated worker.
