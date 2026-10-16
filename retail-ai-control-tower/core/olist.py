"""Olist (retail marketplace) schema: detection, the order_facts table and KPI definitions."""

# Tables + columns that identify an Olist-style retail dataset
REQUIRED = {
    "orders": {"order_id", "customer_id", "order_status", "order_purchase_timestamp",
               "order_delivered_customer_date", "order_estimated_delivery_date"},
    "order_items": {"order_id", "product_id", "seller_id", "price", "freight_value"},
    "order_reviews": {"order_id", "review_score"},
    "customers": {"customer_id", "customer_unique_id", "customer_state"},
}

# Map typical uploaded Kaggle file names to clean table names
FILE_ALIASES = {
    "olist_orders_dataset": "orders",
    "olist_order_items_dataset": "order_items",
    "olist_order_payments_dataset": "order_payments",
    "olist_order_reviews_dataset": "order_reviews",
    "olist_customers_dataset": "customers",
    "olist_sellers_dataset": "sellers",
    "olist_products_dataset": "products",
    "olist_geolocation_dataset": "geolocation",
    "product_category_name_translation": "category_translation",
}


def is_olist(table_columns: dict) -> bool:
    """table_columns: {table_name: set(columns)}"""
    for t, cols in REQUIRED.items():
        if t not in table_columns or not cols.issubset(table_columns[t]):
            return False
    return True


# One row per order with everything the dashboards need.
ORDER_FACTS_SQL = r"""
WITH items AS (
  SELECT i.order_id,
         count(*)                         AS items_count,
         count(DISTINCT i.seller_id)      AS sellers_count,
         sum(i.price)                     AS products_value,
         sum(i.freight_value)             AS freight_value,
         sum(coalesce(p.product_weight_g, 0)) AS weight_g_total,
         arg_max(coalesce(t.product_category_name_english, p.product_category_name, 'unknown'), i.price) AS main_category,
         arg_max(i.seller_id, i.price)    AS seller_id
  FROM order_items i
  LEFT JOIN products p USING (product_id)
  LEFT JOIN category_translation t ON t.product_category_name = p.product_category_name
  GROUP BY 1
), pay AS (
  SELECT order_id, sum(payment_value) AS payment_value,
         arg_max(payment_type, payment_value) AS payment_type,
         max(payment_installments) AS installments
  FROM order_payments GROUP BY 1
), rev AS (
  SELECT order_id, avg(TRY_CAST(review_score AS DOUBLE)) AS review_score
  FROM order_reviews GROUP BY 1
)
SELECT
  o.order_id, o.customer_id, c.customer_unique_id, c.customer_state, c.customer_city,
  o.order_status,
  CAST(o.order_purchase_timestamp AS TIMESTAMP)                 AS purchase_ts,
  CAST(o.order_purchase_timestamp AS DATE)                      AS purchase_date,
  CAST(date_trunc('month', CAST(o.order_purchase_timestamp AS TIMESTAMP)) AS DATE) AS purchase_month,
  CAST(o.order_delivered_customer_date AS TIMESTAMP)            AS delivered_ts,
  CAST(o.order_estimated_delivery_date AS TIMESTAMP)            AS estimated_ts,
  o.order_status IN ('canceled', 'unavailable')                 AS is_canceled,
  o.order_delivered_customer_date IS NOT NULL                   AS is_delivered,
  date_diff('second', CAST(o.order_purchase_timestamp AS TIMESTAMP), CAST(o.order_delivered_customer_date AS TIMESTAMP)) / 86400.0 AS delivery_days,
  date_diff('second', CAST(o.order_purchase_timestamp AS TIMESTAMP), CAST(o.order_estimated_delivery_date AS TIMESTAMP)) / 86400.0 AS estimated_days,
  date_diff('day', CAST(o.order_estimated_delivery_date AS DATE), CAST(o.order_delivered_customer_date AS DATE)) AS delay_days,
  CAST(o.order_delivered_customer_date AS DATE) > CAST(o.order_estimated_delivery_date AS DATE) AS is_late,
  it.items_count, it.sellers_count, it.products_value, it.freight_value,
  it.products_value + it.freight_value                          AS gmv,
  it.freight_value / nullif(it.products_value + it.freight_value, 0) AS freight_share,
  it.weight_g_total, it.main_category, it.seller_id,
  s.seller_state,
  pay.payment_value, pay.payment_type, pay.installments,
  rev.review_score,
  rev.review_score IS NOT NULL                                  AS has_review,
  rev.review_score <= 2                                         AS is_bad_review,
  rev.review_score >= 4                                         AS is_good_review,
  (o.order_delivered_customer_date IS NOT NULL
     AND CAST(o.order_delivered_customer_date AS DATE) <= CAST(o.order_estimated_delivery_date AS DATE)
     AND rev.review_score >= 4)                                 AS is_healthy,
  CASE WHEN gc.lat IS NULL OR gs.lat IS NULL THEN NULL ELSE
    2 * 6371 * asin(sqrt(pow(sin(radians(gs.lat - gc.lat) / 2), 2) +
      cos(radians(gc.lat)) * cos(radians(gs.lat)) * pow(sin(radians(gs.lng - gc.lng) / 2), 2))) END AS distance_km
FROM orders o
LEFT JOIN customers c USING (customer_id)
LEFT JOIN items it USING (order_id)
LEFT JOIN pay USING (order_id)
LEFT JOIN rev USING (order_id)
LEFT JOIN sellers s ON s.seller_id = it.seller_id
LEFT JOIN geolocation gc ON gc.zip_code_prefix = c.customer_zip_code_prefix
LEFT JOIN geolocation gs ON gs.zip_code_prefix = s.seller_zip_code_prefix
"""

# Used by the AI assistant so KPI questions are answered the same way the dashboard does.
KPI_GUIDE = """
KPI definitions for this retail dataset (use table order_facts whenever possible — one row per order):
- Exclude cancelled orders unless asked: WHERE NOT is_canceled.
- Orders = count(*) ; GMV = sum(gmv) (products + freight, in Brazilian reais R$) ; AOV = GMV / Orders.
- On-time delivery rate = avg(CASE WHEN NOT is_late THEN 1 ELSE 0 END) over delivered orders (is_delivered).
- Late order = is_late (delivered after the promised date). delay_days = delivered date − promised date.
- Average delivery days = avg(delivery_days) over delivered orders.
- Average review score = avg(review_score) where has_review. Bad review = review_score <= 2 (is_bad_review). Good = >= 4.
- Healthy GMV (North Star) = sum(gmv) where is_healthy (delivered on time AND review >= 4).
- Healthy GMV share = Healthy GMV / GMV of delivered, reviewed orders.
- Repeat-purchase rate = share of customer_unique_id with 2 or more orders.
- Customers are identified by customer_unique_id (customer_id is per order).
- Product categories: order_facts.main_category (English). Seller: seller_id / seller_state. Customer location: customer_state.
- Time: purchase_ts / purchase_date / purchase_month. Data covers about Sep 2016 – Oct 2018; the last weeks are incomplete.
"""
