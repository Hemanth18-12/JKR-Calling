"""Lightweight S3/MinIO compatible server for local development and testing.
Stores all bucket objects on the local filesystem under .minio_storage/.
Implements standard S3 REST endpoints and MinIO health checks.
"""

import os
from pathlib import Path
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
import uvicorn
import xml.etree.ElementTree as ET

BASE_DIR = Path(__file__).resolve().parents[1] / ".minio_storage"
BASE_DIR.mkdir(parents=True, exist_ok=True)
for b in ["jkr-recordings", "jkr-documents", "jkr-exports"]:
    (BASE_DIR / b).mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Local MinIO / S3 Emulator")

def _s3_error(code: str, message: str, resource: str, status_code: int = 404) -> Response:
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Error>
    <Code>{code}</Code>
    <Message>{message}</Message>
    <Resource>{resource}</Resource>
</Error>"""
    return Response(content=xml, status_code=status_code, media_type="application/xml")

@app.get("/minio/health/live")
@app.get("/minio/health/ready")
def health():
    return PlainTextResponse("OK", status_code=200)

@app.put("/{bucket}")
def create_bucket(bucket: str):
    bucket_dir = BASE_DIR / bucket
    bucket_dir.mkdir(parents=True, exist_ok=True)
    return Response(status_code=200)

@app.head("/{bucket}")
def head_bucket(bucket: str):
    bucket_dir = BASE_DIR / bucket
    if not bucket_dir.exists():
        return _s3_error("NoSuchBucket", "The specified bucket does not exist", f"/{bucket}", status_code=404)
    return Response(status_code=200)

@app.get("/{bucket}")
def list_objects(bucket: str, request: Request):
    bucket_dir = BASE_DIR / bucket
    if not bucket_dir.exists():
        return _s3_error("NoSuchBucket", "The specified bucket does not exist", f"/{bucket}", status_code=404)

    if "location" in request.query_params:
        xml = '<?xml version="1.0" encoding="UTF-8"?><LocationConstraint xmlns="http://s3.amazonaws.com/doc/2006-03-01/">us-east-1</LocationConstraint>'
        return Response(content=xml, media_type="application/xml")

    prefix = request.query_params.get("prefix", "")
    root = ET.Element("ListBucketResult", xmlns="http://s3.amazonaws.com/doc/2006-03-01/")
    ET.SubElement(root, "Name").text = bucket
    ET.SubElement(root, "Prefix").text = prefix
    ET.SubElement(root, "MaxKeys").text = "1000"
    ET.SubElement(root, "IsTruncated").text = "false"

    for p in bucket_dir.rglob("*"):
        if p.is_file():
            key = p.relative_to(bucket_dir).as_posix()
            if prefix and not key.startswith(prefix):
                continue
            contents = ET.SubElement(root, "Contents")
            ET.SubElement(contents, "Key").text = key
            ET.SubElement(contents, "Size").text = str(p.stat().st_size)
            ET.SubElement(contents, "ETag").text = f'"{hash(key)}"'

    xml_str = ET.tostring(root, encoding="utf-8")
    return Response(content=xml_str, media_type="application/xml")

@app.put("/{bucket}/{key:path}")
async def put_object(bucket: str, key: str, request: Request):
    bucket_dir = BASE_DIR / bucket
    bucket_dir.mkdir(parents=True, exist_ok=True)
    file_path = bucket_dir / key
    file_path.parent.mkdir(parents=True, exist_ok=True)
    
    body = await request.body()
    with open(file_path, "wb") as f:
        f.write(body)

    content_type = request.headers.get("content-type", "application/octet-stream")
    meta_path = file_path.with_suffix(file_path.suffix + ".meta")
    with open(meta_path, "w", encoding="utf-8") as f:
        f.write(content_type)

    return Response(status_code=200, headers={"ETag": f'"{hash(body)}"'})

@app.get("/{bucket}/{key:path}")
def get_object(bucket: str, key: str):
    bucket_dir = BASE_DIR / bucket
    file_path = bucket_dir / key
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Object not found")

    content_type = "application/octet-stream"
    meta_path = file_path.with_suffix(file_path.suffix + ".meta")
    if meta_path.exists():
        content_type = meta_path.read_text(encoding="utf-8").strip()

    return FileResponse(file_path, media_type=content_type)

@app.head("/{bucket}/{key:path}")
def head_object(bucket: str, key: str):
    bucket_dir = BASE_DIR / bucket
    file_path = bucket_dir / key
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Object not found")

    content_type = "application/octet-stream"
    meta_path = file_path.with_suffix(file_path.suffix + ".meta")
    if meta_path.exists():
        content_type = meta_path.read_text(encoding="utf-8").strip()

    return Response(
        status_code=200,
        headers={
            "Content-Length": str(file_path.stat().st_size),
            "Content-Type": content_type,
            "ETag": f'"{hash(file_path.name)}"',
        },
    )

@app.delete("/{bucket}/{key:path}")
def delete_object(bucket: str, key: str):
    bucket_dir = BASE_DIR / bucket
    file_path = bucket_dir / key
    if file_path.exists():
        file_path.unlink()
        meta_path = file_path.with_suffix(file_path.suffix + ".meta")
        if meta_path.exists():
            meta_path.unlink()
    return Response(status_code=204)

if __name__ == "__main__":
    port = int(os.environ.get("MINIO_PORT", 9000))
    print(f"Starting MinIO / S3 emulator on port {port}...", flush=True)
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")
