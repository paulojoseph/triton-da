You're building the core matching engine for a trading venue. A full session's order flow has been captured at `/app/events.csv`, one event per line in arrival order, in one of three forms:

- `L,<side>,<id>,<price>,<qty>` — a limit order. `side` is `B` (buy) or `S` (sell); `id` is a unique positive integer; `price` and `qty` are positive integers.
- `M,<side>,<id>,<qty>` — a market order (no price).
- `C,<id>` — cancel the still-resting limit order with that id (a no-op if the order has already filled, was already cancelled, or never rested).

Replay the whole session through a price–time-priority order book starting from empty, and write a summary to `/app/result.json`. An incoming buy matches the lowest-priced resting sells at or below its limit price; a sell matches the highest-priced resting buys at or above its limit price; a market order matches the best available opposite orders at any price. Within one price level the oldest resting order fills first. Each fill trades at the **resting** order's price for the smaller of the two remaining quantities, and partial fills leave the remainder working. A limit order's unfilled remainder rests in the book and is available to later orders; a market order's unfilled remainder is discarded.

Write `/app/engine.py` so that `python3 /app/engine.py` reads `/app/events.csv` and writes `/app/result.json`. The session is large — millions of events — and the verifier enforces a wall-clock budget, so an engine that rescans the book on every event will be far too slow to finish; keep the book state in a form that stays fast as it grows.

`/app/result.json` must be a single JSON object with exactly these fields, all integers (use JSON `null` for an empty book side):

- `trades` — number of individual fills.
- `volume` — total quantity filled across all fills.
- `notional` — sum of `price * quantity` over all fills.
- `resting_orders` — number of orders still live in the book at the end.
- `resting_volume` — total remaining quantity of those orders.
- `resting_id_sum` — sum of the ids of those orders.
- `resting_notional` — sum of `price * remaining_quantity` over those orders.
- `best_bid` — highest resting buy price, or `null`.
- `best_ask` — lowest resting sell price, or `null`.

Worked example. For the four events `L,B,1,100,10`, `L,S,2,101,5`, `L,S,3,99,8`, `M,B,4,6`: order 3 (sell, 99) hits resting buy 1 and fills 8 at price 100, leaving buy 1 with 2; order 2 rests (101 is above the best bid); the market buy 4 fills 5 against order 2 at 101 and discards its last 1. The result is `{"trades": 2, "volume": 13, "notional": 1305, "resting_orders": 1, "resting_volume": 2, "resting_id_sum": 1, "resting_notional": 200, "best_bid": 100, "best_ask": null}`.
