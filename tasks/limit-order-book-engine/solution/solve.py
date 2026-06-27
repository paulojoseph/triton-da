#!/usr/bin/env python3
"""Reference matching engine: reads /app/events.csv, replays the limit order
book with price-time priority, and writes the summary to /app/result.json.

Uses lazy-deletion heaps for best bid/ask, per-price FIFO deques, and an
order-id index, so the whole stream is processed in roughly O(n log n).
"""
import heapq
import json
from collections import deque

EVENTS = "/app/events.csv"
RESULT = "/app/result.json"


def read_events(path):
    events = []
    with open(path) as f:
        for line in f:
            line = line.rstrip("\n")
            if not line:
                continue
            t = line.split(",")
            a = t[0]
            if a == "C":
                events.append(("C", int(t[1])))
            elif a == "M":
                events.append(("M", t[1], int(t[2]), None, int(t[3])))
            else:
                events.append(("L", t[1], int(t[2]), int(t[3]), int(t[4])))
    return events


def run(events):
    bid_levels = {}; bid_qty = {}; bid_heap = []
    ask_levels = {}; ask_qty = {}; ask_heap = []
    loc = {}
    trades = volume = notional = 0

    def best_ask():
        while ask_heap:
            p = ask_heap[0]
            if ask_qty.get(p, 0) > 0:
                return p
            heapq.heappop(ask_heap)
        return None

    def best_bid():
        while bid_heap:
            p = -bid_heap[0]
            if bid_qty.get(p, 0) > 0:
                return p
            heapq.heappop(bid_heap)
        return None

    def rest(side, oid, price, qty):
        node = [oid, qty]
        if side == "B":
            if price not in bid_levels:
                bid_levels[price] = deque(); bid_qty[price] = 0
            if bid_qty[price] == 0:
                heapq.heappush(bid_heap, -price)
            bid_levels[price].append(node); bid_qty[price] += qty
        else:
            if price not in ask_levels:
                ask_levels[price] = deque(); ask_qty[price] = 0
            if ask_qty[price] == 0:
                heapq.heappush(ask_heap, price)
            ask_levels[price].append(node); ask_qty[price] += qty
        loc[oid] = (side, price, node)

    for ev in events:
        if ev[0] == "C":
            n = loc.get(ev[1])
            if n is not None:
                side, price, node = n
                if node[1] > 0:
                    if side == "B":
                        bid_qty[price] -= node[1]
                    else:
                        ask_qty[price] -= node[1]
                    node[1] = 0
                del loc[ev[1]]
            continue
        kind, side, oid, price, qty = ev
        rem = qty
        if side == "B":
            while rem > 0:
                bp = best_ask()
                if bp is None or (kind == "L" and bp > price):
                    break
                dq = ask_levels[bp]; node = dq[0]
                while node[1] == 0:
                    dq.popleft(); node = dq[0]
                f = rem if rem < node[1] else node[1]
                rem -= f; node[1] -= f; ask_qty[bp] -= f
                trades += 1; volume += f; notional += bp * f
                if node[1] == 0:
                    dq.popleft(); loc.pop(node[0], None)
        else:
            while rem > 0:
                bp = best_bid()
                if bp is None or (kind == "L" and bp < price):
                    break
                dq = bid_levels[bp]; node = dq[0]
                while node[1] == 0:
                    dq.popleft(); node = dq[0]
                f = rem if rem < node[1] else node[1]
                rem -= f; node[1] -= f; bid_qty[bp] -= f
                trades += 1; volume += f; notional += bp * f
                if node[1] == 0:
                    dq.popleft(); loc.pop(node[0], None)
        if kind == "L" and rem > 0:
            rest(side, oid, price, rem)

    num = vol = idsum = note = 0
    bb = ba = None
    for oid, (side, price, node) in loc.items():
        q = node[1]
        if q <= 0:
            continue
        num += 1; vol += q; idsum += oid; note += price * q
        if side == "B":
            bb = price if bb is None or price > bb else bb
        else:
            ba = price if ba is None or price < ba else ba
    return {"trades": trades, "volume": volume, "notional": notional,
            "resting_orders": num, "resting_volume": vol, "resting_id_sum": idsum,
            "resting_notional": note, "best_bid": bb, "best_ask": ba}


def main():
    result = run(read_events(EVENTS))
    with open(RESULT, "w") as f:
        json.dump(result, f)


if __name__ == "__main__":
    main()
