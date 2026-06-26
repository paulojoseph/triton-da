import json
import os
import math
import array
from decimal import Decimal, ROUND_HALF_UP

def round_half_up(val, decimals):
    """Computes exact rational round-half-up rounding as required by the specification."""
    fmt = '.' + '0' * decimals if decimals > 0 else '1'
    return float(Decimal(str(val)).quantize(Decimal(fmt), rounding=ROUND_HALF_UP))

def calculate_window_p95(histogram, size):
    """Computes the nearest-rank 95th percentile from a 1001-slot frequency histogram."""
    if size == 0:
        return 0.00
    target_rank = math.ceil(0.95 * size)
    cumulative = 0
    for ms in range(1001):
        cumulative += histogram[ms]
        if cumulative >= target_rank:
            return float(Decimal(str(ms)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))
    return 0.00

def run_optimized_aggregator():
    input_path = "/app/data/system.log"
    output_path = "/app/output.json"
    if not os.path.exists(input_path):
        return

    # Capacidades definidas pela instrução (1.2M global / 400k por serviço)
    G_CAP = 1200000
    S_CAP = 400000

    processed_count = 0
    malformed_count = 0

    # Buffers Circulares (Status: 'B' = unsigned char/1 byte; Latency: 'H' = unsigned short/2 bytes)
    global_status = array.array('B', [0] * G_CAP)
    global_latency = array.array('H', [0] * G_CAP)
    global_head = 0
    global_size = 0
    global_errors = 0
    global_hist = [0] * 1001

    service_status = {s: array.array('B', [0] * S_CAP) for s in ["auth", "gateway", "payment"]}
    service_latency = {s: array.array('H', [0] * S_CAP) for s in ["auth", "gateway", "payment"]}
    service_heads = {"auth": 0, "gateway": 0, "payment": 0}
    service_sizes = {"auth": 0, "gateway": 0, "payment": 0}
    service_errors = {"auth": 0, "gateway": 0, "payment": 0}
    service_hists = {s: [0] * 1001 for s in ["auth", "gateway", "payment"]}

    with open(input_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                # Validação estrita do esquema e tipos
                if set(data.keys()) != {"service", "status", "latency_ms"}:
                    malformed_count += 1
                    continue
                srv = data["service"]
                if srv not in ["auth", "gateway", "payment"]:
                    malformed_count += 1
                    continue
                status = data["status"]
                latency = data["latency_ms"]
                if type(status) is not int or isinstance(status, bool) or \
                   type(latency) is not int or isinstance(latency, bool):
                    malformed_count += 1
                    continue
                if not (100 <= status <= 599) or not (0 <= latency <= 1000):
                    malformed_count += 1
                    continue

                processed_count += 1
                is_err = 1 if status >= 400 else 0

                # Atualização Global
                if global_size == G_CAP:
                    old_err = global_status[global_head]
                    old_lat = global_latency[global_head]
                    global_errors -= old_err
                    global_hist[old_lat] -= 1
                    global_status[global_head] = is_err
                    global_latency[global_head] = latency
                    global_head = (global_head + 1) % G_CAP
                else:
                    idx = (global_head + global_size) % G_CAP
                    global_status[idx] = is_err
                    global_latency[idx] = latency
                    global_size += 1

                global_errors += is_err
                global_hist[latency] += 1

                # Atualização por Serviço
                s_stat = service_status[srv]
                s_lat = service_latency[srv]
                s_head = service_heads[srv]
                s_size = service_sizes[srv]

                if s_size == S_CAP:
                    old_s_err = s_stat[s_head]
                    old_s_lat = s_lat[s_head]
                    service_errors[srv] -= old_s_err
                    service_hists[srv][old_s_lat] -= 1
                    s_stat[s_head] = is_err
                    s_lat[s_head] = latency
                    service_heads[srv] = (s_head + 1) % S_CAP
                else:
                    idx = (s_head + s_size) % S_CAP
                    s_stat[idx] = is_err
                    s_lat[idx] = latency
                    service_sizes[srv] += 1

                service_errors[srv] += is_err
                service_hists[srv][latency] += 1

            except Exception:
                malformed_count += 1

    # Cálculos Finais de Agregação
    output_metrics = {
        "processed_count": processed_count,
        "malformed_count": malformed_count,
        "global_error_rate": float((Decimal(global_errors) / Decimal(global_size)).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)) if global_size > 0 else 0.0000,
        "global_p95_latency_ms": calculate_window_p95(global_hist, global_size)
    }

    for srv in ["auth", "gateway", "payment"]:
        s_size = service_sizes[srv]
        output_metrics[f"{srv}_error_rate"] = float((Decimal(service_errors[srv]) / Decimal(s_size)).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)) if s_size > 0 else 0.0000
        output_metrics[f"{srv}_p95_latency_ms"] = calculate_window_p95(service_hists[srv], s_size)

    with open(output_path, "w") as f:
        json.dump(output_metrics, f, indent=2)

if __name__ == "__main__":
    run_optimized_aggregator()