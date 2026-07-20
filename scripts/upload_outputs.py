import boto3
import os
from pathlib import Path
import json

def upload_file(client, bucket, local_path, remote_key):
    client.upload_file(
        str(local_path),
        bucket,
        remote_key,
        ExtraArgs={
            "ContentType": guess_content_type(local_path),
            "CacheControl": "public, max-age=3600"
        }
    )

def guess_content_type(path):
    suffix = Path(path).suffix.lower()
    if suffix == ".pdf":
        return "application/pdf"
    if suffix == ".html":
        return "text/html; charset=utf-8"
    if suffix == ".json":
        return "application/json; charset=utf-8"
    return "application/octet-stream"

def main():
    bucket = os.environ["R2_BUCKET"]
    public_base = os.environ["R2_PUBLIC_BASE_URL"]

    s3 = boto3.client(
        "s3",
        endpoint_url=f"https://{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto"
    )

    manifest = json.load(open("outputs/manifest.json", encoding="utf-8"))

    for item in manifest["files"]:
        local_path = Path(item["local_path"])
        remote_key = item["remote_key"]
        upload_file(s3, bucket, local_path, remote_key)
        item["public_url"] = f"{public_base}/{remote_key}"

    with open("outputs/uploaded_manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()