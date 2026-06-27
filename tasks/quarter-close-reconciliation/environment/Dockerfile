FROM ubuntu:24.04

WORKDIR /app

RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

COPY sources /app/sources
COPY fx_rates.csv /app/fx_rates.csv

CMD ["bash", "-c", "echo 'Write /app/reconcile.py, then run: python3 /app/reconcile.py'"]
