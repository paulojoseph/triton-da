"""Correlates start/end events into completed requests."""


class Correlator:
    def __init__(self):
        self.open = {}          # id -> start event
        self.completed = []     # list of (svc, is_err, latency)
        self.unmatched = 0

    def feed(self, event):
        if event["phase"] == "start":
            self.open[event["id"]] = event
            return
        start = self.open.get(event["id"])
        if start is None:
            self.unmatched += 1
            return
        latency = event["ts"] - start["ts"]
        is_err = 1 if event["status"] >= 400 else 0
        self.completed.append((event["svc"], is_err, latency))

    def finalize(self):
        return self.completed, self.unmatched
