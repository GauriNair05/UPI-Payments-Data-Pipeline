import os, sys, boto3

BUCKET = os.environ.get("BUCKET")
if not BUCKET:
    sys.exit("Set BUCKET first (see instructions).")
path = "data/raw/upi_transactions.csv"
if not os.path.exists(path):
    sys.exit("Run 00_generate_data.py first.")
boto3.client("s3").upload_file(path, BUCKET, "raw/upi_transactions.csv")
print(f"Uploaded {path} -> s3://{BUCKET}/raw/upi_transactions.csv")
