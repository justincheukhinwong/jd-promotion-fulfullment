"""Construct one row per order from the JD source tables."""
from __future__ import annotations
import gc
import numpy as np
import pandas as pd
from .config import DATA_DIR, FILES, EPS, INVENTORY_CHECK_PREVIOUS_DAY, CHUNKSIZE_INVENTORY
from .reporting import record_table

def standardize_columns(df: pd.DataFrame) -> pd.DataFrame:
    '''Return a copy with lower-case, stripped column names.'''
    out = df.copy()
    out.columns = [str(c).strip().lower() for c in out.columns]
    return out


def read_std(table_name: str, **kwargs) -> pd.DataFrame:
    '''Read one required JD CSV and standardize its column names.'''
    path = DATA_DIR / FILES[table_name]
    if not path.exists():
        raise FileNotFoundError(
            f"Could not find {path}. See data/README.md for input setup."
        )
    return standardize_columns(
        pd.read_csv(path, dtype="string", low_memory=False, **kwargs)
    )


def to_num(s: pd.Series) -> pd.Series:
    '''Convert numeric-looking strings to numbers; '-' becomes missing.'''
    return pd.to_numeric(s.replace("-", np.nan), errors="coerce")


def parse_time(s: pd.Series) -> pd.Series:
    '''Parse timestamps, including values that end with an extra ".0".'''
    return pd.to_datetime(
        s.astype("string").str.replace(r"\.0$", "", regex=True),
        errors="coerce",
    )


def mode_or_first(s: pd.Series):
    '''Return the most common nonmissing value when collapsing order lines.'''
    x = s.dropna()
    if x.empty:
        return np.nan
    modes = x.mode()
    return modes.iloc[0] if not modes.empty else x.iloc[0]


def safe_div(num, den):
    '''Vectorized division that returns missing instead of infinity.'''
    num = np.asarray(num, dtype="float64")
    den = np.asarray(den, dtype="float64")
    out = np.full_like(num, np.nan, dtype="float64")
    np.divide(num, den, out=out, where=np.abs(den) > EPS)
    return out


def clean_category(s: pd.Series) -> pd.Series:
    '''Convert a fixed-effect variable to a string category with explicit missing values.'''
    return s.astype("string").fillna("missing")


def attach_local_inventory_availability(
    order_lines: pd.DataFrame,
) -> pd.DataFrame:
    '''Attach prior-day local availability and the local-stockout proxy.'''
    out = order_lines.copy()
    inv_path = DATA_DIR / FILES["inventory"]

    if not inv_path.is_file():
        raise FileNotFoundError("Missing data/raw/JD_inventory_data.csv; see data/README.md.")

    day_shift = 1 if INVENTORY_CHECK_PREVIOUS_DAY else 0
    out["inventory_check_date"] = (
        out["order_date"] - pd.Timedelta(days=day_shift)
    )

    query = out[
        ["line_id", "sku_id", "dc_des", "inventory_check_date"]
    ].dropna().copy()
    query["dc_des"] = pd.to_numeric(
        query["dc_des"], errors="coerce"
    ).astype("Int64")
    query = query.dropna(subset=["dc_des"])

    # Do not classify dates outside the March inventory window as stockouts.
    query = query[
        query["inventory_check_date"].between(
            pd.Timestamp("2018-03-01"),
            pd.Timestamp("2018-03-31"),
        )
    ].copy()
    if query.empty:
        out["local_inventory_available_line"] = np.nan
        out["local_stockout_line"] = np.nan
        return out

    query["key"] = (
        query["inventory_check_date"].dt.strftime("%Y-%m-%d")
        + "|"
        + query["sku_id"].astype(str)
        + "|"
        + query["dc_des"].astype(str)
    )
    needed_keys = set(query["key"].unique())
    available_keys: set[str] = set()

    print(
        f"Checking {len(needed_keys):,} unique local "
        "SKU–warehouse–date inventory keys ..."
    )
    for i, chunk in enumerate(
        pd.read_csv(
            inv_path,
            chunksize=CHUNKSIZE_INVENTORY,
            low_memory=False,
            dtype="string",
        )
    ):
        inv = standardize_columns(chunk)
        required = {"sku_id", "dc_id", "date"}
        if not required.issubset(inv.columns):
            raise ValueError(
                f"Inventory must contain {required}; found {set(inv.columns)}"
            )
        inv["date"] = pd.to_datetime(inv["date"], errors="coerce")
        inv["dc_id"] = pd.to_numeric(
            inv["dc_id"], errors="coerce"
        ).astype("Int64")
        inv = inv.dropna(subset=["sku_id", "dc_id", "date"])
        inv["key"] = (
            inv["date"].dt.strftime("%Y-%m-%d")
            + "|"
            + inv["sku_id"].astype(str)
            + "|"
            + inv["dc_id"].astype(str)
        )
        matched = inv["key"].isin(needed_keys)
        if matched.any():
            available_keys.update(
                inv.loc[matched, "key"].unique().tolist()
            )
        if (i + 1) % 5 == 0:
            print(
                f"  processed {i + 1:,} chunks; "
                f"matched {len(available_keys):,} keys"
            )
        del inv, chunk
        gc.collect()

    query["local_inventory_available_line"] = (
        query["key"].isin(available_keys).astype(float)
    )
    availability = query[
        ["line_id", "local_inventory_available_line"]
    ].drop_duplicates("line_id")
    out = out.merge(availability, on="line_id", how="left", validate="one_to_one")
    out["local_stockout_line"] = np.where(
        out["local_inventory_available_line"].notna(),
        1.0 - out["local_inventory_available_line"],
        np.nan,
    )
    print(
        f"Matched {len(available_keys):,} available keys out of "
        f"{len(needed_keys):,} checked keys."
    )
    return out
PROMO_ORDER = [
    "none",
    "direct",
    "quantity",
    "bundle",
    "coupon",
    "gift_only",
    "mixed_tie",
]


def assign_dominant_promo(row: pd.Series) -> str:
    '''Classify an order by its largest monetary discount component.'''
    amounts = {
        "direct": float(row.get("direct_discount", 0.0) or 0.0),
        "quantity": float(row.get("quantity_discount", 0.0) or 0.0),
        "bundle": float(row.get("bundle_discount", 0.0) or 0.0),
        "coupon": float(row.get("coupon_discount", 0.0) or 0.0),
    }
    if sum(amounts.values()) <= EPS:
        return "gift_only" if row.get("has_gift", 0) == 1 else "none"
    max_amount = max(amounts.values())
    winners = [
        key
        for key, value in amounts.items()
        if value > EPS and abs(value - max_amount) <= EPS
    ]
    return winners[0] if len(winners) == 1 else "mixed_tie"


def build_order_panel(order_lines: pd.DataFrame) -> pd.DataFrame:
    '''Collapse order lines and attach primary-product information.'''
    d = order_lines.copy()
    if not d["type"].isin([1, 2]).all():
        raise ValueError("Order type must be 1 or 2; unknown types cannot be classified as 1P-only.")

    # The primary item is the line contributing the most original order value.
    primary_cols = [
        "order_id",
        "sku_id",
        "brand_id",
        "attribute1",
        "attribute2",
    ]
    primary = (
        d.sort_values(
            ["order_id", "original_line_value", "line_id"],
            ascending=[True, False, True],
        )
        .drop_duplicates("order_id")
        [primary_cols]
        .rename(
            columns={
                "sku_id": "primary_sku",
                "brand_id": "primary_brand",
                "attribute1": "primary_attribute1",
                "attribute2": "primary_attribute2",
            }
        )
    )

    agg = {
        "order_date": ("order_date", "min"),
        "order_datetime": ("order_datetime", "min"),
        "order_hour": ("order_hour", mode_or_first),
        "dc_des": ("dc_des", mode_or_first),
        "n_lines": ("sku_id", "size"),
        "n_skus": ("sku_id", "nunique"),
        "units": ("quantity", "sum"),
        "revenue": ("final_line_revenue", "sum"),
        "original_value": ("original_line_value", "sum"),
        "total_discount": ("discount_line_total", "sum"),
        "direct_discount": ("direct_discount_line", "sum"),
        "quantity_discount": ("quantity_discount_line", "sum"),
        "bundle_discount": ("bundle_discount_line", "sum"),
        "coupon_discount": ("coupon_discount_line", "sum"),
        "has_direct": ("has_direct_line", "max"),
        "has_quantity": ("has_quantity_line", "max"),
        "has_bundle": ("has_bundle_line", "max"),
        "has_coupon": ("has_coupon_line", "max"),
        "has_gift": ("gift_line", "max"),
        "remote_any": ("remote_fulfill_line", "max"),
        "remote_rate": ("remote_fulfill_line", "mean"),
        "local_stockout_any": ("local_stockout_line", "max"),
        "local_stockout_rate": ("local_stockout_line", "mean"),
        "any_1p": (
            "type",
            lambda s: int(
                (pd.to_numeric(s, errors="coerce") == 1).any()
            ),
        ),
        "any_3p": (
            "type",
            lambda s: int(
                (pd.to_numeric(s, errors="coerce") == 2).any()
            ),
        ),
    }
    panel = (
        d.groupby("order_id", observed=True)
        .agg(**agg)
        .reset_index()
        .merge(primary, on="order_id", how="left", validate="one_to_one")
    )

    panel["discount_depth"] = safe_div(
        panel["total_discount"], panel["original_value"]
    )
    panel["discount_depth"] = panel["discount_depth"].clip(0, 2)
    panel["dominant_promo"] = panel.apply(
        assign_dominant_promo, axis=1
    )
    panel["dominant_promo"] = pd.Categorical(
        panel["dominant_promo"],
        categories=PROMO_ORDER,
        ordered=True,
    )
    panel["type_mix"] = np.select(
        [
            panel["any_1p"].eq(1) & panel["any_3p"].eq(1),
            panel["any_1p"].eq(1),
            panel["any_3p"].eq(1),
        ],
        ["mixed_1p_3p", "1p_only", "3p_only"],
        default="unknown",
    )
    panel["order_date_str"] = pd.to_datetime(
        panel["order_date"]
    ).dt.strftime("%Y-%m-%d")
    panel["log_delivery_hours"] = np.nan
    panel["log_original_value"] = np.log1p(
        panel["original_value"].clip(lower=0)
    )
    panel["log_units"] = np.log1p(panel["units"].clip(lower=0))

    # This fallback product cell is intentionally more specific than brand alone.
    panel["brand_attribute_cell"] = (
        clean_category(panel["primary_brand"])
        + "|a1="
        + clean_category(panel["primary_attribute1"])
        + "|a2="
        + clean_category(panel["primary_attribute2"])
    )
    for col in [
        "primary_sku",
        "brand_attribute_cell",
        "order_date_str",
        "order_hour",
        "dc_des",
    ]:
        panel[col] = clean_category(panel[col])
    return panel


def attach_delivery(
    order_panel: pd.DataFrame,
    delivery: pd.DataFrame,
) -> pd.DataFrame:
    '''Merge JD Logistics package timestamps and calculate delivery hours.'''
    d = delivery.copy()
    for col in ["ship_out_time", "arr_station_time", "arr_time"]:
        if col in d.columns:
            d[col] = parse_time(d[col])
    if "package_id" not in d.columns:
        d["package_id"] = d["order_id"]

    delivery_agg = (
        d.groupby("order_id", observed=True)
        .agg(
            n_packages=("package_id", "nunique"),
            last_arrival_time=("arr_time", "max"),
        )
        .reset_index()
    )
    out = order_panel.merge(delivery_agg, on="order_id", how="left", validate="one_to_one")
    out["jd_logistics"] = out["n_packages"].notna().astype(int)
    out["delivery_hours"] = (
        out["last_arrival_time"] - out["order_datetime"]
    ).dt.total_seconds() / 3600
    out.loc[
        (out["delivery_hours"] < 0)
        | (out["delivery_hours"] > 24 * 30),
        "delivery_hours",
    ] = np.nan
    out["log_delivery_hours"] = np.log1p(
        out["delivery_hours"].clip(lower=0)
    )
    return out


def load_order_panel() -> pd.DataFrame:
    """Validate joins, audit numeric inputs, and attach inventory and delivery outcomes."""
    record_table.sku_labels = {}
    print("Reading JD CSV files ...")
    skus = read_std("skus")
    orders_raw = read_std("orders")
    delivery = read_std("delivery")
    network = read_std("network")

    for df in [skus, orders_raw, delivery]:
        for col in ["order_id", "sku_id", "package_id"]:
            if col in df.columns:
                df[col] = df[col].astype("string")

    orders = orders_raw.copy()
    orders["line_id"] = np.arange(len(orders), dtype="int64")
    orders["order_date"] = pd.to_datetime(
        orders["order_date"], errors="coerce"
    )
    orders["order_datetime"] = parse_time(orders["order_time"])
    orders["order_hour"] = (
        orders["order_datetime"].dt.hour.astype("Int64")
    )

    numeric_order_cols = [
        "quantity",
        "type",
        "original_unit_price",
        "final_unit_price",
        "direct_discount_per_unit",
        "quantity_discount_per_unit",
        "bundle_discount_per_unit",
        "coupon_discount_per_unit",
        "gift_item",
        "dc_ori",
        "dc_des",
    ]
    for col in numeric_order_cols:
        if col in orders.columns:
            orders[col] = to_num(orders[col])


    input_audit = pd.DataFrame({
        "column": numeric_order_cols,
        "missing_values": [orders[c].isna().sum() for c in numeric_order_cols],
        "negative_values": [orders[c].lt(0).sum() for c in numeric_order_cols],
    })
    record_table("00_input_quality", input_audit)
    if orders["order_id"].isna().any():
        raise ValueError("Order identifiers are required before aggregation.")

    orders["quantity"] = orders["quantity"].fillna(1).clip(lower=0)
    orders["gift_item"] = orders["gift_item"].fillna(0)

    discount_unit_cols = [
        "direct_discount_per_unit",
        "quantity_discount_per_unit",
        "bundle_discount_per_unit",
        "coupon_discount_per_unit",
    ]
    for col in discount_unit_cols:
        if col not in orders.columns:
            orders[col] = 0.0
        orders[col] = to_num(orders[col]).fillna(0).clip(lower=0)

    orders["original_line_value"] = (
        to_num(orders["original_unit_price"])
        .fillna(0)
        .clip(lower=0)
        * orders["quantity"]
    )
    orders["final_line_revenue"] = (
        to_num(orders["final_unit_price"])
        .fillna(0)
        .clip(lower=0)
        * orders["quantity"]
    )
    for mechanism in ["direct", "quantity", "bundle", "coupon"]:
        orders[f"{mechanism}_discount_line"] = (
            orders[f"{mechanism}_discount_per_unit"]
            * orders["quantity"]
        )
        orders[f"has_{mechanism}_line"] = (
            orders[f"{mechanism}_discount_line"].gt(EPS).astype(int)
        )
    orders["gift_line"] = orders["gift_item"].gt(0).astype(int)
    orders["discount_line_total"] = orders[
        [
            "direct_discount_line",
            "quantity_discount_line",
            "bundle_discount_line",
            "coupon_discount_line",
        ]
    ].sum(axis=1)

    identity_error = (
        orders["original_line_value"]
        - orders["final_line_revenue"]
        - orders["discount_line_total"]
    )
    identity_check = pd.DataFrame(
        {
            "n_lines": [len(orders)],
            "mean_abs_error": [identity_error.abs().mean()],
            "median_abs_error": [identity_error.abs().median()],
            "p95_abs_error": [identity_error.abs().quantile(0.95)],
            "max_abs_error": [identity_error.abs().max()],
        }
    )
    record_table("00_discount_identity_check", identity_check)

    print(
        {
            "skus": skus.shape,
            "orders_raw": orders_raw.shape,
            "delivery": delivery.shape,
            "network": network.shape,
        }
    )

    sku_cols = [
        col
        for col in [
            "sku_id",
            "brand_id",
            "attribute1",
            "attribute2",
        ]
        if col in skus.columns
    ]
    # Preserve agreed attributes; mark conflicting duplicate attributes as missing.
    if skus["sku_id"].isna().any():
        raise ValueError("SKU reference identifiers must be nonmissing.")
    attribute_columns = [c for c in sku_cols if c != "sku_id"]
    conflicts = skus.groupby("sku_id")[attribute_columns].nunique(dropna=False).gt(1)
    skus2 = skus[sku_cols].drop_duplicates("sku_id").set_index("sku_id")
    for column in attribute_columns:
        skus2.loc[conflicts[column], column] = pd.NA
    conflicted_keys = conflicts.index[conflicts.any(axis=1)]
    record_table("00_sku_reference_audit", pd.DataFrame({
        "source_rows": [len(skus)],
        "unique_skus": [len(skus2)],
        "skus_with_conflicting_attributes": [len(conflicted_keys)],
        "order_lines_using_conflicted_skus": [orders["sku_id"].isin(conflicted_keys).sum()],
    }))
    skus2 = skus2.reset_index()
    for col in ["attribute1", "attribute2"]:
        if col in skus2.columns:
            skus2[col] = to_num(skus2[col])
        else:
            skus2[col] = np.nan
    if "brand_id" not in skus2.columns:
        skus2["brand_id"] = "missing"
    skus2["brand_id"] = clean_category(skus2["brand_id"])
    orders = orders.merge(skus2, on="sku_id", how="left", validate="many_to_one")

    network2 = network.copy()
    network2["dc_id"] = to_num(network2["dc_id"])
    network2["region_id"] = to_num(network2["region_id"])
    dc_region = (
        network2[["dc_id", "region_id"]]
        .dropna()
        .drop_duplicates()
    )
    orders = orders.merge(
        dc_region.rename(
            columns={
                "dc_id": "dc_ori",
                "region_id": "ori_region_id",
            }
        ),
        on="dc_ori",
        how="left",
        validate="many_to_one",
    )
    orders = orders.merge(
        dc_region.rename(
            columns={
                "dc_id": "dc_des",
                "region_id": "des_region_id",
            }
        ),
        on="dc_des",
        how="left",
        validate="many_to_one",
    )
    orders["remote_fulfill_line"] = np.where(
        orders["dc_ori"].notna() & orders["dc_des"].notna(),
        orders["dc_ori"].ne(orders["dc_des"]).astype(float),
        np.nan,
    )
    orders = attach_local_inventory_availability(orders)

    order_panel = build_order_panel(orders)
    order_panel = attach_delivery(order_panel, delivery)

    panel_overview = pd.DataFrame(
        {
            "n_orders": [len(order_panel)],
            "n_primary_skus": [order_panel["primary_sku"].nunique()],
            "share_1p_only": [
                order_panel["type_mix"].eq("1p_only").mean()
            ],
            "remote_order_rate": [order_panel["remote_any"].mean()],
            "local_stockout_proxy_rate": [
                order_panel["local_stockout_any"].mean()
            ],
            "jd_logistics_coverage": [
                order_panel["jd_logistics"].mean()
            ],
            "median_delivery_hours_jd": [
                order_panel["delivery_hours"].median()
            ],
        }
    )
    record_table("01_order_panel_overview", panel_overview)


    return order_panel
