"""Reference limit-order-book engine + deterministic event generator.
Verifier-only (never shipped in the image). Computes the golden result and
writes the messy event stream the agent's program must process.
"""
import heapq
import random
from collections import deque


def run(events):
    """events: list of tuples. ('L',side,oid,price,qty) | ('M',side,oid,qty) | ('C',oid)."""
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
        if side == 'B':
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
        if ev[0] == 'C':
            n = loc.get(ev[1])
            if n is not None:
                side, price, node = n
                if node[1] > 0:
                    if side == 'B':
                        bid_qty[price] -= node[1]
                    else:
                        ask_qty[price] -= node[1]
                    node[1] = 0
                del loc[ev[1]]
            continue
        kind, side, oid, price, qty = ev
        rem = qty
        if side == 'B':
            while rem > 0:
                bp = best_ask()
                if bp is None or (kind == 'L' and bp > price):
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
                if bp is None or (kind == 'L' and bp < price):
                    break
                dq = bid_levels[bp]; node = dq[0]
                while node[1] == 0:
                    dq.popleft(); node = dq[0]
                f = rem if rem < node[1] else node[1]
                rem -= f; node[1] -= f; bid_qty[bp] -= f
                trades += 1; volume += f; notional += bp * f
                if node[1] == 0:
                    dq.popleft(); loc.pop(node[0], None)
        if kind == 'L' and rem > 0:
            rest(side, oid, price, rem)

    num = vol = idsum = note = 0
    bb = ba = None
    for oid, (side, price, node) in loc.items():
        q = node[1]
        if q <= 0:
            continue
        num += 1; vol += q; idsum += oid; note += price * q
        if side == 'B':
            bb = price if bb is None or price > bb else bb
        else:
            ba = price if ba is None or price < ba else ba
    return {"trades": trades, "volume": volume, "notional": notional,
            "resting_orders": num, "resting_volume": vol, "resting_id_sum": idsum,
            "resting_notional": note, "best_bid": bb, "best_ask": ba}


def generate(seed, n):
    """Deterministic adversarial stream: clustered prices (level recycling),
    frequent cancels, market sweeps, partial fills, crossing limits."""
    rng = random.Random(seed)
    events = []
    oid = 0
    recent = deque(maxlen=4000)
    mid = 10000
    for _ in range(n):
        r = rng.random()
        oid += 1
        if r < 0.14 and recent:
            events.append(('C', rng.choice(recent)))
        elif r < 0.22:
            side = 'B' if rng.random() < 0.5 else 'S'
            events.append(('M', side, oid, None, rng.randint(1, 60)))
        else:
            side = 'B' if rng.random() < 0.5 else 'S'
            off = int(rng.gauss(0, 7))
            price = mid + (off if side == 'S' else -off) + rng.randint(-3, 3)
            price = price if price > 0 else 1
            events.append(('L', side, oid, price, rng.randint(1, 50)))
            recent.append(oid)
        mid += rng.randint(-1, 1)
    return events


def write_events(events, path):
    with open(path, "w") as f:
        out = []
        for ev in events:
            if ev[0] == 'C':
                out.append(f"C,{ev[1]}")
            elif ev[0] == 'M':
                out.append(f"M,{ev[1]},{ev[2]},{ev[4]}")
            else:
                out.append(f"L,{ev[1]},{ev[2]},{ev[3]},{ev[4]}")
        f.write("\n".join(out) + "\n")
