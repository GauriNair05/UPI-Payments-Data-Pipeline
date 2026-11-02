CREATE DATABASE IF NOT EXISTS upi_db;

-- ===== TABLES =====
CREATE EXTERNAL TABLE upi_db.fact_transactions (
  txn_id string, txn_ts string, date_key int, txn_hour int, txn_type string,
  amount_inr double, status string, failure_reason string,
  sender_key string, receiver_key string,
  sender_bank_id int, receiver_bank_id int, category_id int,
  sender_state string, device_type string,
  is_flagged int, is_high_value int, is_night int
)
PARTITIONED BY (txn_month string)
STORED AS PARQUET
LOCATION 's3://upi-pipeline/curated/fact_transactions/';

MSCK REPAIR TABLE upi_db.fact_transactions;

CREATE EXTERNAL TABLE upi_db.dim_bank (bank_id int, bank_name string)
STORED AS PARQUET
LOCATION 's3://upi-pipeline/curated/dim_bank/';

CREATE EXTERNAL TABLE upi_db.dim_category (category_id int, category_name string)
STORED AS PARQUET
LOCATION 's3://upi-pipeline/curated/dim_category/';

CREATE EXTERNAL TABLE upi_db.dim_date (
  date_key int, full_date string, day_name string,
  month_num int, quarter int, is_weekend int
)
STORED AS PARQUET
LOCATION 's3://upi-pipeline/curated/dim_date/';


SELECT COUNT(*) FROM upi_db.fact_transactions;


WITH monthly AS (
  SELECT txn_month,
         COUNT(*) AS txns,
         ROUND(SUM(CASE WHEN status = 'SUCCESS' THEN amount_inr ELSE 0 END), 2) AS success_value_inr,
         ROUND(100.0 * COUNT_IF(status = 'SUCCESS') / COUNT(*), 2) AS success_rate_pct
  FROM upi_db.fact_transactions
  GROUP BY txn_month
)
SELECT txn_month, txns, success_value_inr, success_rate_pct,
       ROUND(100.0 * (success_value_inr - LAG(success_value_inr) OVER (ORDER BY txn_month))
             / LAG(success_value_inr) OVER (ORDER BY txn_month), 2) AS mom_growth_pct
FROM monthly
ORDER BY txn_month;

SELECT b.bank_name,
       COUNT(*) AS txns,
       ROUND(100.0 * COUNT_IF(f.status = 'FAILED') / COUNT(*), 2) AS failure_rate_pct,
       RANK() OVER (ORDER BY 1.0 * COUNT_IF(f.status = 'FAILED') / COUNT(*) DESC) AS failure_rank
FROM upi_db.fact_transactions f
JOIN upi_db.dim_bank b ON f.sender_bank_id = b.bank_id
GROUP BY b.bank_name
ORDER BY failure_rank;

WITH spend AS (
  SELECT f.sender_state, c.category_name, SUM(f.amount_inr) AS total_spend
  FROM upi_db.fact_transactions f
  JOIN upi_db.dim_category c ON f.category_id = c.category_id
  WHERE f.status = 'SUCCESS' AND f.txn_type IN ('P2M', 'BILL_PAYMENT')
  GROUP BY f.sender_state, c.category_name
),
ranked AS (
  SELECT sender_state, category_name, total_spend,
         RANK() OVER (PARTITION BY sender_state ORDER BY total_spend DESC) AS rnk
  FROM spend
)
SELECT sender_state, category_name, ROUND(total_spend, 2) AS total_spend_inr, rnk
FROM ranked
WHERE rnk <= 3
ORDER BY sender_state, rnk;

SELECT f.txn_type, d.is_weekend, COUNT(*) AS txns, ROUND(AVG(f.amount_inr), 2) AS avg_ticket_inr
FROM upi_db.fact_transactions f
JOIN upi_db.dim_date d ON f.date_key = d.date_key
WHERE f.status = 'SUCCESS'
GROUP BY f.txn_type, d.is_weekend
ORDER BY f.txn_type, d.is_weekend;


SELECT c.category_name, f.is_night, COUNT(*) AS txns, SUM(f.is_flagged) AS flagged,
       ROUND(100.0 * SUM(f.is_flagged) / COUNT(*), 3) AS flag_rate_pct
FROM upi_db.fact_transactions f
JOIN upi_db.dim_category c ON f.category_id = c.category_id
GROUP BY c.category_name, f.is_night
ORDER BY flag_rate_pct DESC
LIMIT 10;



SELECT SUM(amount_inr) FROM upi_db.fact_transactions;
SELECT SUM(amount_inr) FROM upi_db.fact_transactions WHERE txn_month = '2025-06';
