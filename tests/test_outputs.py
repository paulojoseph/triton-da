import os
import json
import time
import subprocess
import pytest
import psutil
from decimal import Decimal, ROUND_HALF_UP

def round_half_up(val, decimals):
    """Computes exact rational round-half-up rounding as required by the specification."""
    fmt = '.' + '0' * decimals if decimals > 0 else '1'
    return float(Decimal(str(val)).quantize(Decimal(fmt), rounding=ROUND_HALF_UP))

def generate_large_stress_log(file_path):
    """Generates a highly-orchestrated full lookback window dataset with scaled capacities."""
    with open(file_path, "w") as f:
        processed_count = 0
        malformed_count = 0
        loop_idx = 0
        service_counts = {"auth": 0, "gateway": 0, "payment": 0}

        while processed_count < 1500000 or malformed_count < 150000:
            if loop_idx % 12 == 0:
                f.write("    \n")
                loop_idx += 1
                continue

            if loop_idx % 15 == 0 and malformed_count < 150000:
                f.write('{"service": "auth", "status": true, "latency_ms": 100}\n')
                malformed_count += 1
                loop_idx += 1
                continue

            if processed_count < 1500000:
                srvs = ["auth", "gateway", "payment"]
                srv = srvs[processed_count % 3]
                s_count = service_counts[srv]

                if s_count < 400000:
                    status = 200
                    latency = 100
                else:
                    win_idx = s_count - 400000
                    if srv == "auth":
                        status = 500 if win_idx < 16680 else 200
                    else:
                        status = 500 if win_idx < 16670 else 200

                    if win_idx < 379995:
                        latency = 150
                    elif win_idx == 379995:
                        latency = 946
                    elif win_idx == 379996:
                        latency = 947
                    elif win_idx == 379997:
                        latency = 948
                    elif win_idx == 379998:
                        latency = 949
                    elif win_idx == 379999:
                        latency = 950
                    elif win_idx == 380000:
                        latency = 951
                    elif win_idx == 380001:
                        latency = 952
                    elif win_idx == 380002:
                        latency = 953
                    elif win_idx == 380003:
                        latency = 954
                    else:
                        latency = 980

                f.write(f'{{"service": "{srv}", "status": {status}, "latency_ms": {latency}}}\n')
                service_counts[srv] += 1
                processed_count += 1
                loop_idx += 1
            else:
                loop_idx += 1

def generate_short_stress_log(file_path):
    """Generates a deterministic dataset where sliding lookback windows are partially full."""
    with open(file_path, "w") as f:
        processed_count = 0
        malformed_count = 0
        loop_idx = 0
        service_counts = {"auth": 0, "gateway": 0, "payment": 0}

        while processed_count < 3000 or malformed_count < 300:
            if loop_idx % 12 == 0:
                f.write("    \n")
                loop_idx += 1
                continue

            if loop_idx % 15 == 0 and malformed_count < 300:
                f.write('{"service": "auth", "status": true, "latency_ms": 100}\n')
                malformed_count += 1
                loop_idx += 1
                continue

            if processed_count < 3000:
                srvs = ["auth", "gateway", "payment"]
                srv = srvs[processed_count % 3]
                s_count = service_counts[srv]

                if srv == "auth":
                    status = 500 if s_count < 125 else 200
                elif srv == "gateway":
                    status = 500 if s_count < 125 else 200
                else:
                    status = 500 if s_count < 126 else 200

                if s_count < 949:
                    latency = 150
                elif s_count == 949:
                    latency = 950
                else:
                    latency = 980

                f.write(f'{{"service": "{srv}", "status": {status}, "latency_ms": {latency}}}\n')
                service_counts[srv] += 1
                processed_count += 1
                loop_idx += 1
            else:
                loop_idx += 1

def get_peak_memory_and_run(cmd, timeout=60):
    proc = subprocess.Popen(cmd, shell=True)
    p = psutil.Process(proc.pid)
    peak_rss = 0
    while proc.poll() is None:
        try:
            mem = p.memory_info().rss
            for child in p.children(recursive=True):
                mem += child.memory_info().rss
            if mem > peak_rss:
                peak_rss = mem
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
        time.sleep(0.05)
    return proc.returncode, peak_rss / (1024 * 1024)

def enforce_stdlib_and_schema_constraints():
    with open("/app/aggregator.py", "r", encoding="utf-8") as f:
        content = f.read()
    assert "pandas" not in content, "Forbidden third-party module 'pandas' detected!"
    assert "numpy" not in content, "Forbidden third-party module 'numpy' detected!"

def test_log_streaming_functional_and_memory_bounds():
    log_dir = "/app/data"
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "system.log")
    output_file = "/app/output.json"

    if os.path.exists(output_file):
        os.remove(output_file)

    generate_large_stress_log(log_file)

    return_code, peak_memory_mb = get_peak_memory_and_run("python3 /app/aggregator.py")

    assert return_code == 0, "Log stream processing crashed during execution."
    assert os.path.exists(output_file), "Output artifact /app/output.json was not created."
    enforce_stdlib_and_schema_constraints()

    with open(output_file, "r") as f:
        results = json.load(f)

    assert len(results) == 10
    assert results["processed_count"] == 1500000
    assert results["malformed_count"] == 150000
    assert results["global_error_rate"] == 0.1251 # 50020 / 400000 = 0.12505 -> 0.1251
    assert results["global_p95_latency_ms"] == 150.00
    assert results["auth_error_rate"] == 0.1668
    assert results["auth_p95_latency_ms"] == 950.00
    assert results["gateway_error_rate"] == 0.1667
    assert results["gateway_p95_latency_ms"] == 950.00
    assert results["payment_error_rate"] == 0.1667
    assert results["payment_p95_latency_ms"] == 950.00

    print(f"Peak RSS Memory Registered: {peak_memory_mb:.2f} MB")
    assert peak_memory_mb < 64.0, f"Memory budget exceeded! Used {peak_memory_mb:.2f}MB RAM."

def test_partially_full_windows_edge_case():
    log_dir = "/app/data"
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "system.log")
    output_file = "/app/output.json"

    if os.path.exists(output_file):
        os.remove(output_file)

    generate_short_stress_log(log_file)

    return_code, _ = get_peak_memory_and_run("python3 /app/aggregator.py")
    assert return_code == 0
    enforce_stdlib_and_schema_constraints()

    with open(output_file, "r") as f:
        results = json.load(f)

    assert len(results) == 10
    assert results["processed_count"] == 3000
    assert results["malformed_count"] == 300
    assert results["global_error_rate"] == 0.1253
    assert results["global_p95_latency_ms"] == 950.00
    assert results["auth_error_rate"] == 0.1250
    assert results["auth_p95_latency_ms"] == 950.00
    assert results["gateway_error_rate"] == 0.1250
    assert results["gateway_p95_latency_ms"] == 950.00
    assert results["payment_error_rate"] == 0.1260
    assert results["payment_p95_latency_ms"] == 950.00

def test_empty_log_edge_case():
    log_dir = "/app/data"
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "system.log")
    output_file = "/app/output.json"

    if os.path.exists(output_file):
        os.remove(output_file)

    with open(log_file, "w") as f:
        f.write("\n\n   \n\n")

    return_code, _ = get_peak_memory_and_run("python3 /app/aggregator.py")
    assert return_code == 0
    enforce_stdlib_and_schema_constraints()

    with open(output_file, "r") as f:
        results = json.load(f)

    assert len(results) == 10
    assert results["processed_count"] == 0
    assert results["malformed_count"] == 0
    assert results["global_error_rate"] == 0.0000
    assert results["global_p95_latency_ms"] == 0.00
    assert results["auth_error_rate"] == 0.0000
    assert results["auth_p95_latency_ms"] == 0.00
    assert results["gateway_error_rate"] == 0.0000
    assert results["gateway_p95_latency_ms"] == 0.00
    assert results["payment_error_rate"] == 0.0000
    assert results["payment_p95_latency_ms"] == 0.00