Our log aggregator at `/app/aggregator.py` crashes with Out-of-Memory faults on large files. Please refactor it into a memory-bounded stream processor that reads `/app/data/system.log` line-by-line, ensuring that peak resident memory (RSS) stays strictly under 64MB using only the Python standard library.

Ignore blank lines. A line is valid if it parses as a JSON object with exactly these keys: `service` (either "auth", "gateway", or "payment"), `status` (strict integer 100–599), and `latency_ms` (strict integer 0–1000). Any other non-blank line violates our strict primitive type contract and is considered malformed, which should increment a counter and be skipped gracefully.

To capture localized load shifts, track metrics concurrently inside independent rolling lookback windows: a global window of the last 1,200,000 valid records, and separate service windows of the last 400,000 valid records per service type. At the end of the stream, write a flat JSON object to `/app/output.json` containing exactly these ten keys:
- `processed_count` and `malformed_count`: Total file-wide counts.
- `{window}_error_rate` (rounded to 4 decimal places): Ratio of records with status >= 400 within that final window.
- `{window}_p95_latency_ms` (rounded to 2 decimal places): Nearest-rank 95th percentile of latency within that final window.

Replace `{window}` with `global`, `auth`, `gateway`, and `payment`. For windows with fewer items than their maximum capacity, calculate metrics over the available items. Empty windows default to 0.0000 for error rates and 0.00 for percentiles. All float rounding must use exact rational round-half-up math.