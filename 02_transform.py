import hashlib, json, os, shutil
import numpy as np
import pandas as pd

RAW, OUT, REJ = "data/raw/upi_transactions.csv", "data/curated", "data/rejected"
SALT = os.environ.get("HASH_SALT", "change-me-salt")
MIN_TS, MAX_TS = pd.Timestamp("2025-01-01"), pd.Timestamp("2026-01-01")
UPI_LIMIT = 100_000
VALID_TYPES = {"P2P", "P2M", "BILL_PAYMENT", "RECHARGE"}
VALID_STATUS = {"SUCCESS", "FAILED", "PENDING"}
REQUIRED = ["txn_id", "txn_type", "status", "sender_vpa", "receiver_vpa",
            "sender_bank", "receiver_bank", "merchant_category", "sender_state"]

BANK_ALIASES = {
    "sbi": "State Bank of India", "state bank of india": "State Bank of India",
    "hdfc": "HDFC Bank", "hdfc bank": "HDFC Bank",
    "icici": "ICICI Bank", "icici bank": "ICICI Bank",
    "axis": "Axis Bank", "axis bank": "Axis Bank",
    "kotak mahindra bank": "Kotak Mahindra Bank", "kotak": "Kotak Mahindra Bank",
    "pnb": "Punjab National Bank", "punjab national bank": "Punjab National Bank",
    "bob": "Bank of Baroda", "bank of baroda": "Bank of Baroda",
    "canara bank": "Canara Bank", "union bank of india": "Union Bank of India",
    "indusind bank": "IndusInd Bank", "yes bank": "Yes Bank", "idfc first bank": "IDFC First Bank",
}

def std_bank(s):
    key = s.str.strip().str.lower()
    return key.map(BANK_ALIASES).fillna(s.str.strip().str.title())

def pseudonymize(s):
    mapping = {v: hashlib.sha256((SALT + v).encode()).hexdigest()[:16] for v in s.unique()}
    return s.map(mapping)

# ---------------- Extract ----------------
df = pd.read_csv(RAW, dtype=str)
raw_rows = len(df)
df["txn_type"] = df["txn_type"].str.strip().str.upper()
df["status"] = df["status"].str.strip().str.upper()
df["amount_inr"] = pd.to_numeric(df["amount_inr"], errors="coerce")
df["ts"] = pd.to_datetime(df["timestamp"], format="%Y-%m-%d %H:%M:%S", errors="coerce")

# ---------------- Validate (rejects go to quarantine with a reason) ----------------
df["reject_reason"] = pd.Series([None] * len(df), dtype="object")
def reject(mask, reason):
    idx = mask & df["reject_reason"].isna()
    df.loc[idx, "reject_reason"] = reason

reject(df[REQUIRED].isna().any(axis=1), "missing_required_field")
reject(df.duplicated("txn_id", keep="first"), "duplicate_txn_id")
reject(df["ts"].isna(), "invalid_timestamp")
reject((df["ts"] < MIN_TS) | (df["ts"] >= MAX_TS), "timestamp_out_of_range")
reject(df["amount_inr"].isna(), "invalid_amount")
reject(df["amount_inr"] <= 0, "non_positive_amount")
reject(df["amount_inr"] > UPI_LIMIT, "over_upi_limit")
reject(df["sender_vpa"] == df["receiver_vpa"], "self_transfer")
reject(~df["txn_type"].isin(VALID_TYPES) | ~df["status"].isin(VALID_STATUS), "invalid_type_or_status")

rej = df[df["reject_reason"].notna()]
clean = df[df["reject_reason"].isna()].copy()
breakdown = {k: int(v) for k, v in rej["reject_reason"].value_counts().items()}

# ---------------- Transform ----------------
for c in ["sender_bank", "receiver_bank"]:
    clean[c] = std_bank(clean[c])
clean["sender_key"] = pseudonymize(clean["sender_vpa"])        
clean["receiver_key"] = pseudonymize(clean["receiver_vpa"])
clean["txn_ts"] = clean["ts"].dt.strftime("%Y-%m-%d %H:%M:%S")
clean["date_key"] = clean["ts"].dt.strftime("%Y%m%d").astype("int32")
clean["txn_hour"] = clean["ts"].dt.hour.astype("int32")
clean["txn_month"] = clean["ts"].dt.strftime("%Y-%m")
clean["is_high_value"] = (clean["amount_inr"] >= 10000).astype("int32")
clean["is_night"] = (clean["txn_hour"] <= 5).astype("int32")
clean["is_flagged"] = pd.to_numeric(clean["fraud_flag"], errors="coerce").fillna(0).astype("int32")

# ---------------- Dimensions ----------------
banks = sorted(set(clean.sender_bank) | set(clean.receiver_bank))
bank_id = {b: i + 1 for i, b in enumerate(banks)}
dim_bank = pd.DataFrame({"bank_id": pd.Series(list(bank_id.values()), dtype="int32"),
                         "bank_name": pd.Series(list(bank_id.keys()), dtype="string")})
cats = sorted(clean.merchant_category.unique())
cat_id = {c: i + 1 for i, c in enumerate(cats)}
dim_category = pd.DataFrame({"category_id": pd.Series(list(cat_id.values()), dtype="int32"),
                             "category_name": pd.Series(list(cat_id.keys()), dtype="string")})
dates = pd.to_datetime(sorted(clean["ts"].dt.normalize().unique()))
dim_date = pd.DataFrame({
    "date_key": dates.strftime("%Y%m%d").astype("int32"),
    "full_date": pd.Series(dates.strftime("%Y-%m-%d"), dtype="string"),
    "day_name": pd.Series(dates.day_name(), dtype="string"),
    "month_num": dates.month.astype("int32"),
    "quarter": dates.quarter.astype("int32"),
    "is_weekend": (dates.dayofweek >= 5).astype("int32"),
})


fact = pd.DataFrame({
    "txn_id": clean["txn_id"].astype("string"),
    "txn_ts": clean["txn_ts"].astype("string"),
    "date_key": clean["date_key"],
    "txn_hour": clean["txn_hour"],
    "txn_type": clean["txn_type"].astype("string"),
    "amount_inr": clean["amount_inr"].astype("float64"),
    "status": clean["status"].astype("string"),
    "failure_reason": clean["failure_reason"].astype("string"),
    "sender_key": clean["sender_key"].astype("string"),
    "receiver_key": clean["receiver_key"].astype("string"),
    "sender_bank_id": clean["sender_bank"].map(bank_id).astype("int32"),
    "receiver_bank_id": clean["receiver_bank"].map(bank_id).astype("int32"),
    "category_id": clean["merchant_category"].map(cat_id).astype("int32"),
    "sender_state": clean["sender_state"].astype("string"),
    "device_type": clean["device_type"].astype("string"),
    "is_flagged": clean["is_flagged"],
    "is_high_value": clean["is_high_value"],
    "is_night": clean["is_night"],
    "txn_month": clean["txn_month"],
})

shutil.rmtree(OUT, ignore_errors=True)
shutil.rmtree(REJ, ignore_errors=True)
fact.to_parquet(f"{OUT}/fact_transactions", partition_cols=["txn_month"], index=False, engine="pyarrow")
for name, frame in [("dim_bank", dim_bank), ("dim_category", dim_category), ("dim_date", dim_date)]:
    os.makedirs(f"{OUT}/{name}")
    frame.to_parquet(f"{OUT}/{name}/{name}.parquet", index=False)
os.makedirs(REJ)
rej[["txn_id", "timestamp", "txn_type", "status", "amount_inr", "reject_reason"]] \
    .to_csv(f"{REJ}/rejected_transactions.csv", index=False)

# ---------------- Metrics ----------------
ok = fact[fact.status == "SUCCESS"]
metrics = {
    "raw_rows": raw_rows,
    "clean_rows": len(fact),
    "rejected_rows": len(rej),
    "rejected_pct": round(100 * len(rej) / raw_rows, 2),
    "rejection_breakdown": breakdown,
    "success_rate_pct": round(100 * len(ok) / len(fact), 2),
    "flagged_pct": round(100 * fact.is_flagged.mean(), 3),
    "successful_value_inr": round(float(ok.amount_inr.sum()), 2),
    "banks": len(dim_bank), "categories": len(dim_category), "days": len(dim_date),
}
os.makedirs("data", exist_ok=True)
json.dump(metrics, open("data/metrics.json", "w"), indent=2)
print(json.dumps(metrics, indent=2))
