"""Pipeline configuration."""

DATA_DIR = "/app/data"
OUTPUT_PATH = "/app/output.json"

SERVICES = ("auth", "gateway", "payment")

# Rolling window capacities, in completed requests.
GLOBAL_WINDOW = 5000
SERVICE_WINDOW = 2000
