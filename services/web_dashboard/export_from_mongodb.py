import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
import re

from pymongo import MongoClient
from bson import json_util


def _repo_root() -> Path:
    # services/web_dashboard/<this_file> -> repo root is 2 levels up
    return Path(__file__).resolve().parents[2]


def _default_out_dir() -> Path:
    # Keep exports under raw/ so user can share the snapshot as “raw data”.
    return _repo_root() / "data" / "raw" / "mongodb_export"


def _redact_mongo_uri(uri: str) -> str:
    # Redact credentials if present: mongodb://user:pass@host -> mongodb://user:***@host
    return re.sub(r"^(mongodb(?:\\+srv)?://[^:/@]+:)([^@]+)(@)", r"\\1***\\3", uri)


def export_collection(db, collection_name: str, out_path: Path) -> int:
    collection = db[collection_name]

    out_path.parent.mkdir(parents=True, exist_ok=True)
    exported = 0

    cursor = collection.find({}, no_cursor_timeout=True)
    try:
        with out_path.open("w", encoding="utf-8") as f:
            for doc in cursor:
                f.write(json_util.dumps(doc, ensure_ascii=False))
                f.write("\n")
                exported += 1
    finally:
        cursor.close()

    return exported


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export MongoDB collections to data/mongodb_export as JSONL."
    )
    parser.add_argument(
        "--mongo-uri",
        default=os.getenv("MONGO_URI", "mongodb://localhost:27017/"),
        help="MongoDB connection URI (or set env var MONGO_URI).",
    )
    parser.add_argument(
        "--db",
        default=os.getenv("MONGO_DB", "zakatsight"),
        help="Database name (default: zakatsight; or env var MONGO_DB).",
    )
    parser.add_argument(
        "--collections",
        nargs="*",
        default=["penerimaan", "mustahiq", "penyaluran"],
        help="Collections to export (default: penerimaan mustahiq penyaluran).",
    )
    parser.add_argument(
        "--out-dir",
        default=str(_default_out_dir()),
        help="Output directory under repo (default: data/raw/mongodb_export).",
    )
    args = parser.parse_args()

    print(f"Connecting to MongoDB: {_redact_mongo_uri(args.mongo_uri)}")
    try:
        client = MongoClient(args.mongo_uri, serverSelectionTimeoutMS=5000)
        client.server_info()  # trigger connection check
    except Exception as e:
        print(f"Failed to connect to MongoDB: {e}")
        return 1

    db = client[args.db]
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    exported_at = (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
    meta = {
        "exported_at": exported_at,
        "mongo_uri": "(redacted)",
        "db": args.db,
        "collections": [],
    }

    total = 0
    for name in args.collections:
        out_path = out_dir / f"{name}.jsonl"
        print(f"Exporting '{args.db}.{name}' -> {out_path}")
        try:
            count = export_collection(db, name, out_path)
        except Exception as e:
            print(f"  [ERROR] Failed exporting collection '{name}': {e}")
            continue
        print(f"  [OK] {count} documents")
        meta["collections"].append({"name": name, "documents": count, "file": out_path.name})
        total += count

    meta_path = out_dir / "export_metadata.json"
    meta_path.write_text(json_util.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\nDone. Total exported documents: {total}")
    print(f"Output directory: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
