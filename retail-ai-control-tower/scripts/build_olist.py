"""Build the default Olist dataset (parquet tables + order_facts) from the raw Kaggle CSV files.

Usage:  python scripts/build_olist.py <folder_with_olist_csvs> [output_dataset_folder]
"""
import json
import sys
from datetime import datetime
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.olist import ORDER_FACTS_SQL  # noqa: E402

FILES = {
    "orders": "olist_orders_dataset.csv",
    "order_items": "olist_order_items_dataset.csv",
    "order_payments": "olist_order_payments_dataset.csv",
    "order_reviews": "olist_order_reviews_dataset.csv",
    "customers": "olist_customers_dataset.csv",
    "sellers": "olist_sellers_dataset.csv",
    "products": "olist_products_dataset.csv",
    "geolocation": "olist_geolocation_dataset.csv",
    "category_translation": "product_category_name_translation.csv",
}


def build(src: Path, out: Path):
    out.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    for t, f in FILES.items():
        p = (src / f).as_posix()
        if t == "geolocation":
            # 1M rows -> one row per zip prefix (average point)
            con.execute(f"""CREATE TABLE geolocation AS
                SELECT geolocation_zip_code_prefix AS zip_code_prefix,
                       avg(geolocation_lat) AS lat, avg(geolocation_lng) AS lng,
                       mode(geolocation_city) AS city, mode(geolocation_state) AS state
                FROM read_csv_auto('{p}', header=true) GROUP BY 1""")
        elif t == "order_reviews":
            con.execute(f"CREATE TABLE {t} AS SELECT * FROM read_csv('{p}', header=true, auto_detect=true, quote='\"', escape='\"', ignore_errors=true, strict_mode=false)")
        else:
            con.execute(f"CREATE TABLE {t} AS SELECT * FROM read_csv_auto('{p}', header=true)")
    con.execute(f"CREATE TABLE order_facts AS {ORDER_FACTS_SQL}")
    tables = list(FILES) + ["order_facts"]
    for t in tables:
        con.execute(f"COPY {t} TO '{(out / (t + '.parquet')).as_posix()}' (FORMAT parquet, COMPRESSION zstd)")
    meta = {"name": "Olist e-commerce (default)", "kind": "olist", "default": True,
            "created": datetime.now().isoformat(timespec="seconds"),
            "description": "Brazilian E-Commerce Public Dataset by Olist — ~100k orders, 2016–2018.",
            "tables": {t: con.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in tables}}
    (out / "meta.json").write_text(json.dumps(meta, indent=2))
    print(json.dumps(meta["tables"], indent=2))


if __name__ == "__main__":
    src = Path(sys.argv[1])
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "data" / "datasets" / "olist"
    build(src, out)
