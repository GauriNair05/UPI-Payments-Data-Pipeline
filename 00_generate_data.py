import os
import numpy as np
import pandas as pd

N = int(os.environ.get("N_ROWS", 500_000))
rng = np.random.default_rng(42)
os.makedirs("data/raw", exist_ok=True)

BANKS = ["State Bank of India", "HDFC Bank", "ICICI Bank", "Axis Bank", "Kotak Mahindra Bank",
         "Punjab National Bank", "Bank of Baroda", "Canara Bank", "Union Bank of India",
         "IndusInd Bank", "Yes Bank", "IDFC First Bank"]
BANK_P = np.array([22, 17, 14, 11, 6, 7, 6, 5, 4, 3, 2, 3], float); BANK_P /= BANK_P.sum()
BANK_VARIANTS = {
    "State Bank of India": ["SBI", "state bank of india", " State Bank of India "],
    "HDFC Bank": ["hdfc bank", "HDFC", "HDFC BANK"],
    "ICICI Bank": ["icici bank", "ICICI"],
    "Axis Bank": ["AXIS BANK", "axis bank"],
    "Punjab National Bank": ["PNB", "punjab national bank"],
    "Bank of Baroda": ["BoB", "bank of baroda"],
}
STATES = ["Maharashtra", "Karnataka", "Tamil Nadu", "Kerala", "Delhi", "Uttar Pradesh", "Gujarat",
          "West Bengal", "Telangana", "Rajasthan", "Madhya Pradesh", "Bihar", "Punjab", "Haryana",
          "Andhra Pradesh"]
STATE_P = np.array([14, 10, 9, 6, 8, 12, 8, 7, 6, 5, 4, 4, 3, 2, 2], float); STATE_P /= STATE_P.sum()
P2M_CATS = ["Grocery", "Food & Dining", "Fuel", "Travel", "Entertainment", "Healthcare", "Shopping"]
P2M_P = np.array([25, 22, 12, 12, 8, 6, 15], float); P2M_P /= P2M_P.sum()
BILL_CATS = ["Utilities", "Insurance", "Education", "Credit Card"]
FAIL_REASONS = ["Insufficient funds", "Bank server down", "Incorrect PIN", "Timeout", "Daily limit exceeded"]
HOUR_P = np.array([1,1,1,1,1,2,3,5,6,7,7,7,7,7,7,7,8,9,10,10,9,7,4,2], float); HOUR_P /= HOUR_P.sum()

# ---- type, category ----
typ = rng.choice(["P2P", "P2M", "BILL_PAYMENT", "RECHARGE"], N, p=[0.45, 0.35, 0.12, 0.08])
cat = np.empty(N, dtype=object)
cat[typ == "P2P"] = "Person to Person"
cat[typ == "RECHARGE"] = "Mobile Recharge"
m = typ == "P2M";          cat[m] = rng.choice(P2M_CATS, m.sum(), p=P2M_P)
m = typ == "BILL_PAYMENT"; cat[m] = rng.choice(BILL_CATS, m.sum())

# ---- amount (INR) ----
amount = np.round(np.clip(rng.lognormal(6.0, 1.1, N), 1, 100000), 2)
m = typ == "BILL_PAYMENT"; amount[m] = np.round(np.clip(rng.lognormal(7.2, 0.7, m.sum()), 50, 100000), 2)
m = typ == "RECHARGE";     amount[m] = rng.choice([99, 199, 299, 399, 599, 749], m.sum())

# ---- timestamps across 2025 ----
days = rng.integers(0, 365, N)
hours = rng.choice(24, N, p=HOUR_P)
secs = rng.integers(0, 3600, N)
ts = pd.Timestamp("2025-01-01") + pd.to_timedelta(days * 86400 + hours * 3600 + secs, unit="s")

# ---- parties ----
sender = np.array([f"user{i}@upi" for i in rng.integers(1, 60000, N)], dtype=object)
receiver = np.empty(N, dtype=object)
m = typ == "P2P";      receiver[m] = [f"user{i}@upi" for i in rng.integers(1, 60000, m.sum())]
m = typ == "P2M";      receiver[m] = [f"merchant{i}@upi" for i in rng.integers(1, 4000, m.sum())]
m = typ == "BILL_PAYMENT"; receiver[m] = [f"biller{i}@upi" for i in rng.integers(1, 300, m.sum())]
m = typ == "RECHARGE"; receiver[m] = [f"operator{i}@upi" for i in rng.integers(1, 6, m.sum())]

status = rng.choice(["SUCCESS", "FAILED", "PENDING"], N, p=[0.955, 0.04, 0.005])
reason = np.where(status == "FAILED", rng.choice(FAIL_REASONS, N), None)

p_fraud = 0.0005 + 0.004 * (amount > 20000) + 0.002 * (hours < 6)
fraud = (rng.random(N) < p_fraud).astype(int)

df = pd.DataFrame({
    "txn_id": [f"TXN{i:09d}" for i in range(1, N + 1)],
    "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S"),
    "txn_type": typ,
    "merchant_category": cat,
    "amount_inr": amount,
    "status": status,
    "failure_reason": reason,
    "sender_vpa": sender,
    "receiver_vpa": receiver,
    "sender_bank": rng.choice(BANKS, N, p=BANK_P),
    "receiver_bank": rng.choice(BANKS, N, p=BANK_P),
    "sender_state": rng.choice(STATES, N, p=STATE_P),
    "device_type": rng.choice(["Android", "iOS"], N, p=[0.8, 0.2]),
    "fraud_flag": fraud,
})

# ---- inject dirty data ----
def pick(frac):
    return rng.choice(N, int(N * frac), replace=False)

df.loc[pick(0.003), "amount_inr"] = 0                       # zero/negative amounts
neg = pick(0.002); df.loc[neg, "amount_inr"] = -df.loc[neg, "amount_inr"]
df.loc[pick(0.002), "amount_inr"] = np.nan                  # missing amount
df.loc[pick(0.001), "amount_inr"] = 250000                  # above UPI limit
df.loc[pick(0.002), "sender_vpa"] = None                    # missing sender
bad_ts = pick(0.002); df.loc[bad_ts, "timestamp"] = rng.choice(["NA", "2025-13-45 99:99:99", ""], len(bad_ts))
df.loc[pick(0.001), "timestamp"] = "2030-01-01 10:00:00"    # out-of-range timestamp
st = pick(0.001); df.loc[st, "receiver_vpa"] = df.loc[st, "sender_vpa"]   # self transfer
low = pick(0.01); df.loc[low, "status"] = df.loc[low, "status"].str.lower()
for col in ["sender_bank", "receiver_bank"]:
    for i in pick(0.03):
        v = BANK_VARIANTS.get(df.at[i, col])
        if v:
            df.at[i, col] = v[rng.integers(len(v))]

dups = df.sample(frac=0.005, random_state=1)                # duplicate events
df = pd.concat([df, dups]).sample(frac=1, random_state=2).reset_index(drop=True)

df.to_csv("data/raw/upi_transactions.csv", index=False)
print(f"Wrote data/raw/upi_transactions.csv with {len(df):,} rows")
