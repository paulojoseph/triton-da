FROM ubuntu:24.04

WORKDIR /app

RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

COPY engine.py /app/engine.py
COPY data /app/data

CMD ["python3", "/app/engine.py"]
