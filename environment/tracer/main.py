"""Trace-latency pipeline entry point.

Reads sharded request logs, correlates start/end events into completed
requests, and writes rolling-window error-rate and p95 latency metrics to
/app/output.json.
"""
import os
import json

import config
import ingest
import correlate
import metrics


def run():
    corr = correlate.Correlator()
    malformed = 0

    for name in os.listdir(config.DATA_DIR):
        if not (name.startswith("shard-") and name.endswith(".log")):
            continue
        path = os.path.join(config.DATA_DIR, name)
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                event = ingest.parse_event(line)
                if event is None:
                    malformed += 1
                    continue
                corr.feed(event)

    completed, unmatched = corr.finalize()

    result = {
        "processed_count": len(completed),
        "malformed_count": malformed,
        "unmatched_count": unmatched,
    }
    result.update(
        metrics.compute(
            completed,
            config.SERVICES,
            config.GLOBAL_WINDOW,
            config.SERVICE_WINDOW,
        )
    )

    with open(config.OUTPUT_PATH, "w") as f:
        json.dump(result, f, indent=2)


if __name__ == "__main__":
    run()
