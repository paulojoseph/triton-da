import json
import os

def run_naive_aggregator():
    """
    Semente propositalmente fragil e ingenua.
    Nao faz validacao de tipos, esquemas ou contagem de malformed.
    """
    input_path = "/app/data/system.log"
    output_path = "/app/output.json"
    if not os.path.exists(input_path):
        return

    # Sinks de memoria originais (Le tudo e acumula arrays sem limites)
    with open(input_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    processed_count = 0
    errors = 0
    latencies = []

    for line in lines:
        # Codigo fragil: explode se a linha for invalida ou vazia
        data = json.loads(line)
        processed_count += 1
        if data["status"] >= 400:
            errors += 1
        latencies.append(data["latency_ms"])

    latencies.sort()
    # P95 falho usando indexacao de ponto flutuante truncada
    p95_latency = latencies[int(0.95 * len(latencies))] if latencies else 0.0

    with open(output_path, "w") as f:
        json.dump({
            "processed_count": processed_count,
            "malformed_count": 0,
            "error_rate": round(errors / processed_count, 4) if processed_count else 0.0,
            "p95_latency_ms": round(p95_latency, 2)
        }, f, indent=2)

if __name__ == "__main__":
    run_naive_aggregator()