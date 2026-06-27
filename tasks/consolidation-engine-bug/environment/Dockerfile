FROM ubuntu:24.04

WORKDIR /app

RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

# The engine, its sample data, and the known-correct sample output.
COPY app /app

CMD ["bash", "-c", "echo 'Run: python3 /app/consolidate.py  (then compare /app/output.json to /app/expected_sample.json)'"]
