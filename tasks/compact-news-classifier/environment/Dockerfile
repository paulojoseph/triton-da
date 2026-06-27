FROM ubuntu:24.04

WORKDIR /app

RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --break-system-packages -r /app/requirements.txt

COPY data /app/data

CMD ["bash", "-c", "echo 'Train a model on /app/data/train.jsonl and save /app/model.pkl'"]
