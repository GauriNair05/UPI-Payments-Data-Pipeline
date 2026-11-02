import json
import pandas as pd

fact = pd.read_parquet("data/curated/fact_transactions")
bank = pd.read_parquet("data/curated/dim_bank")
cat = pd.read_parquet("data/curated/dim_category")
date = pd.read_parquet("data/curated/dim_date")
m = json.load(open("data/metrics.json"))
checks = []

def add(name, ok, detail=""):
    checks.append((name, "PASS" if ok else "FAIL", detail))

add("row count matches pipeline metrics", len(fact) == m["clean_rows"], f"{len(fact)} vs {m['clean_rows']}")
add("raw = clean + rejected", m["raw_rows"] == m["clean_rows"] + m["rejected_rows"],
    f"{m['raw_rows']} = {m['clean_rows']} + {m['rejected_rows']}")
add("txn_id unique", fact.txn_id.is_unique)
for c in ["txn_id", "txn_ts", "amount_inr", "status", "sender_key", "receiver_key",
          "sender_bank_id", "receiver_bank_id", "category_id", "date_key"]:
    n = int(fact[c].isna().sum())
    add(f"no nulls in {c}", n == 0, f"{n} nulls")
add("amount in (0, 1,00,000]", bool(((fact.amount_inr > 0) & (fact.amount_inr <= 100000)).all()))
add("status valid", bool(fact.status.isin(["SUCCESS", "FAILED", "PENDING"]).all()))
add("no self transfers", int((fact.sender_key == fact.receiver_key).sum()) == 0)
add("sender_bank_id exists in dim_bank", bool(fact.sender_bank_id.isin(bank.bank_id).all()))
add("receiver_bank_id exists in dim_bank", bool(fact.receiver_bank_id.isin(bank.bank_id).all()))
add("category_id exists in dim_category", bool(fact.category_id.isin(cat.category_id).all()))
add("date_key exists in dim_date", bool(fact.date_key.isin(date.date_key).all()))
add("no raw VPAs in curated data", not fact.sender_key.str.contains("@").any())

report = "\n".join(f"{s:5} | {n:42} | {d}" for n, s, d in checks)
print(report)
open("data/quality_report.txt", "w").write(report)
if any(s == "FAIL" for _, s, _ in checks):
    raise SystemExit("Data quality checks FAILED")
