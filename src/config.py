"""Project paths and prespecified analysis settings."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "raw"
TABLE_DIR = ROOT / "results"
FIGURE_DIR = ROOT / "figures"
INVENTORY_CHECK_PREVIOUS_DAY = True
CHUNKSIZE_INVENTORY = 2_000_000
MAX_MODEL_ROWS = None
RANDOM_SEED = 20260727
MIN_ORDERS_PER_PROMO_PER_SKU = 3
MIN_STRICT_OVERLAP_SKUS = 20
MIN_MODEL_ROWS = 500
MIN_CLUSTERS = 20
FE_TOL = 1e-8
FE_MAX_ITER = 200
EPS = 1e-9
FILES = {
    "skus": "JD_sku_data.csv", "orders": "JD_order_data.csv",
    "delivery": "JD_delivery_data.csv", "inventory": "JD_inventory_data.csv",
    "network": "JD_network_data.csv",
}
MODEL_FE = ["brand_attribute_cell", "order_date_str", "order_hour", "dc_des"]
OUTCOMES = ["remote_any", "local_stockout_any", "log_delivery_hours"]

INPUTS = {name: DATA_DIR / filename for name, filename in FILES.items()}
