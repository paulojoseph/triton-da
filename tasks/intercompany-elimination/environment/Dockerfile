FROM ubuntu:24.04

WORKDIR /app

RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

COPY data /app/data

CMD ["bash", "-c", "echo 'Write /app/consolidate.py, then run: python3 /app/consolidate.py'"]
