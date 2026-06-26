A telemetry aggregator at `/app/aggregator.py` was written as a naive batch job: it loads the entire event log into memory and crashes with out-of-memory faults, and it ignores out-of-order delivery. Rewrite it into a streaming, memory-bounded processor. Running `python3 /app/aggregator.py` must read `/app/data/events.log` line by line and write `/app/output.json`, with peak resident memory (RSS) staying strictly under 64 MB, using only the Python standard library.

Each non-blank line is one event, in arrival order. A valid event is a JSON object with exactly the keys `ts` (event time, a strict integer number of seconds ≥ 0), `svc` (one of `"auth"`, `"gateway"`, `"payment"`), `status` (strict integer 100–599), and `latency_ms` (strict integer 0–1000). Booleans are not integers. Ignore blank (whitespace-only) lines. Any other non-blank line is malformed: count it and skip it.

Events arrive out of order in event time, so the aggregator tracks a watermark. Before processing a valid event, let `watermark` be the largest `ts` among all valid events earlier in the stream (including any that were themselves dropped as late); the first valid event has no earlier events and is never late. A valid event is late when `watermark − ts > 30` — strictly more than 30 seconds behind the watermark. Late events are dropped: count them in `late_count` and exclude them from every window and metric. Every valid, non-late event is accepted and assigned to the 60-second tumbling window whose start second is `ts − (ts mod 60)`.

Write a flat JSON object to `/app/output.json` with exactly these four top-level keys:

- `processed_count`: number of accepted events. `malformed_count`: number of malformed lines. `late_count`: number of dropped late events. (All are file-wide totals.)
- `windows`: an object mapping each window-start second that holds at least one accepted event — written as a decimal string, e.g. `"1740"` — to an object with exactly `count` (integer number of accepted events in the window), `error_rate` (4 decimal places: the fraction of the window's accepted events whose `status` is ≥ 400), and `p95_latency_ms` (2 decimal places: the nearest-rank 95th percentile of the window's accepted `latency_ms` values, i.e. the value at 1-based index `ceil(0.95 × count)` of those latencies sorted ascending).

All rounding must use exact round-half-up.
