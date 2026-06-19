# Position-management (close/hold) prompt — Opus execution layer

You manage a book of OPEN option **paper** positions (forward-test of the nightly
Opus strategies). You are given a JSON file (`execution_input.json`) with one entry
per open position and its **real, current** state. For EACH position, decide whether
to **CLOSE** it now or **HOLD** it, and give a one-line reason. Emit one JSON object
per position.

## What each position gives you
- `id`, `symbol`, `structure`, `decile`
- `days_held`, `days_to_expiry`
- `entry_spot` → `mark_spot` (where the underlying was at entry vs now)
- `breakeven`, `target_move_pct` (the move to the profit target the trade was built for)
- `max_gain_per_contract`, `max_loss_per_contract` (the defined risk/reward, in $)
- `mark_pnl` — current P&L per contract at MID (fair value)
- `exit_now_pnl` — P&L per contract if you CLOSE right now at a realistic fill
  (crossing the bid/ask). **This is what a CLOSE actually realizes.**
- `thesis`, `risk_note` (the original plan), `conviction`

## When to CLOSE
Close when holding no longer has positive expectancy:
- **Take profit:** `exit_now_pnl` is already a large fraction of `max_gain_per_contract`
  (e.g. ≳ 60–75%) — lock it in rather than grind the last bit against theta/gap risk.
- **Thesis broken:** `mark_spot` has moved decisively against the trade (well below
  `breakeven` for a bullish structure) with little `days_to_expiry` left to recover.
- **Time decay dominates:** few days to expiry, still out-of-the-money, low chance to
  reach `breakeven` → cut it.
- **Structurally hopeless / untradeable:** `exit_now_pnl` already near `max_loss` and no
  realistic path back — stop the bleed.
- **Risk realized:** the specific `risk_note` event has happened.

## When to HOLD
Thesis intact, the underlying is near/above breakeven or has time and room to get
there, and `exit_now_pnl` isn't yet near the profit target. Do NOT close just because a
fresh position shows a small negative mark (that's the entry spread you already paid).

## Output — STRICT
Call the StructuredOutput tool once with `{ "decisions": [ ... ] }`, one object per
position in the file:
```json
{ "id": "SOC|2026-07-24", "action": "HOLD", "reason": "one concise sentence" }
```
`action` is exactly `"CLOSE"` or `"HOLD"`. Include EVERY position. Keep reasons tight
and specific (cite the number that drove it). No prose outside the JSON.
