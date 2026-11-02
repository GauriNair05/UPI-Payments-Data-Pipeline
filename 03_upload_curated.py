import os, sys, boto3

BUCKET = os.environ.get("BUCKET")
if not BUCKET:
    sys.exit("Set BUCKET first.")
s3 = boto3.client("s3")
n = 0
for folder in ["data/curated", "data/rejected"]:
    for root, _, files in os.walk(folder):
        for f in files:
            if f.startswith((".", "_")) or f.endswith(".crc"):
                continue
            local = os.path.join(root, f)
            key = os.path.relpath(local, "data").replace(os.sep, "/")
            s3.upload_file(local, BUCKET, key)
            n += 1
print(f"Uploaded {n} files to s3://{BUCKET}/ (curated/ and rejected/)")
