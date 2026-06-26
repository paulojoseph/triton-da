The request-tracing pipeline at `/app/tracer/` is broken: on production-sized inputs it exhausts memory, and it reports incorrect metrics. Repair it so that running `python3 /app/tracer/main.py` reads the sharded logs under `/app/data/`, computes the metrics below, and writes them to `/app/output.json`. Peak resident memory (RSS) must stay strictly under 64 MB, using only the Python standard library.

`/app/data/` holds one or more shard files named `shard-*.log`. Concatenate them in ascending filename order, with lines in file order, to form a single event stream. Ignore blank (whitespace-only) lines. A valid event is a JSON object with exactly the keys `id` (non-empty string), `svc` (one of `"auth"`, `"gateway"`, `"payment"`), `phase` (one of `"start"` or `"end"`), `ts` (strict integer millisecond timestamp ≥ 0), and `status` (strict integer 100–599). Booleans are not integers. Any other non-blank line is malformed: count it and skip it.

Correlate events into requests by `id`, processing the stream in order. A `start` opens a request. An `end` whose `id` is currently open closes it, producing one completed request whose `svc` is taken from its `start`, whose `latency_ms` is `end.ts − start.ts`, and which is errored iff its `end` `status` is ≥ 400. A `start` whose `id` is already open is malformed. An `end` with no currently-open `id`, and any request still open at the end of the stream, is unmatched.

Track metrics over rolling windows of completed requests, in the order requests complete: a global window of the last 5,000 completed requests, and a per-service window of the last 2,000 completed requests for each of `auth`, `gateway`, and `payment`. Write a flat JSON object to `/app/output.json` with exactly these eleven keys:

- `processed_count`: number of completed requests; `malformed_count`; `unmatched_count` (file-wide totals).
- `{window}_error_rate` (4 decimal places): errored requests ÷ window size.
- `{window}_p95_latency_ms` (2 decimal places): nearest-rank 95th percentile — the `latency_ms` at 1-based index `ceil(0.95 × size)` of the window's latencies sorted ascending.

Replace `{window}` with `global`, `auth`, `gateway`, and `payment`. When a window holds fewer items than its capacity, compute over the available items; an empty window gives `0.0000` and `0.00`. All rounding must use exact round-half-up.
