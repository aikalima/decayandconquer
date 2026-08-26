#!/usr/bin/env python3
"""Download Massive.com flat files (options day aggregates) from S3.

Downloads gzip CSV files containing all US options contracts for each
trading day. Files are saved to a local directory, one per day.

Usage:
    # Download all options day aggs for January 2025
    python scripts/download_flat_files.py --year 2025 --month 1

    # Download a specific date
    python scripts/download_flat_files.py --date 2025-06-15

    # Download all of 2025
    python scripts/download_flat_files.py --year 2025

    # Download and filter to specific tickers only
    python scripts/download_flat_files.py --year 2025 --month 1 --tickers SPY,AAPL,NVDA

    # List available files for a month
    python scripts/download_flat_files.py --year 2025 --month 1 --list

    # Custom output directory
    python scripts/download_flat_files.py --year 2025 --month 1 --output ./my_data
"""

import argparse
import gzip
import io
import os
import sys
from datetime import date, timedelta
from pathlib import Path

import boto3
from botocore.config import Config

# Massive flat-file S3 endpoint.
S3_ENDPOINT = "https://files.massive.com"
S3_BUCKET = "flatfiles"

# S3 path for options day aggregates
OPTIONS_PREFIX = "us_options_opra/day_aggs_v1"

DEFAULT_OUTPUT = Path(__file__).parent.parent / "app" / "data" / "flat_files"


def load_project_env() -> None:
    """Load repo-root .env when the downloader is run directly."""
    env_path = Path(__file__).parent.parent.parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, val = line.split("=", 1)
            os.environ.setdefault(key.strip(), val.strip().strip("'\""))


def env_first(*names: str) -> str:
    for name in names:
        value = os.environ.get(name, "")
        if value:
            return value
    return ""


def get_s3_client():
    load_project_env()
    access_key = env_first("MASSIVE_S3_ACCESS_KEY", "MASSIVE_FLATFILES_ACCESS_KEY", "S3_ACCESS_KEY")
    secret_key = env_first("MASSIVE_S3_SECRET_KEY", "MASSIVE_FLATFILES_SECRET_KEY", "S3_SECRET_KEY")
    if not access_key or not secret_key:
        raise ValueError(
            "Massive flat files require S3 credentials. Set MASSIVE_S3_ACCESS_KEY "
            "and MASSIVE_S3_SECRET_KEY in the repo-root .env."
        )

    return boto3.client(
        "s3",
        endpoint_url=S3_ENDPOINT,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=Config(signature_version="s3v4"),
    )


def list_files(client, year: int, month: int | None = None) -> list[str]:
    """List available flat files for a year/month."""
    if month:
        prefix = f"{OPTIONS_PREFIX}/{year}/{month:02d}/"
    else:
        prefix = f"{OPTIONS_PREFIX}/{year}/"

    keys = []
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=prefix):
        for obj in page.get("Contents", []):
            keys.append(obj["Key"])
    return sorted(keys)


def download_file(client, key: str, output_dir: Path, tickers: set[str] | None = None):
    """Download a single flat file and optionally filter by ticker."""
    filename = key.split("/")[-1]  # e.g., 2025-01-06.csv.gz
    output_path = output_dir / filename

    if output_path.exists():
        print(f"  SKIP {filename} (already exists)")
        return

    print(f"  Downloading {key} ...", end=" ", flush=True)
    response = client.get_object(Bucket=S3_BUCKET, Key=key)
    raw_bytes = response["Body"].read()
    size_mb = len(raw_bytes) / (1024 * 1024)

    if tickers:
        # Decompress, filter, re-compress
        with gzip.open(io.BytesIO(raw_bytes), "rt") as f:
            lines = f.readlines()

        if not lines:
            print(f"empty file")
            return

        header = lines[0]
        filtered = [header]
        for line in lines[1:]:
            # ticker is the first column: O:AAPL250117C00100000
            # Extract underlying from OCC symbol: O:{TICKER}{date}...
            t = line.split(",", 1)[0]
            if t.startswith("O:"):
                underlying = ""
                for ch in t[2:]:
                    if ch.isalpha():
                        underlying += ch
                    else:
                        break
                if underlying in tickers:
                    filtered.append(line)

        # Save filtered as gzip
        buf = io.BytesIO()
        with gzip.open(buf, "wt") as f:
            f.writelines(filtered)
        output_path.write_bytes(buf.getvalue())
        print(f"{size_mb:.1f}MB -> {len(filtered)-1} rows (filtered)")
    else:
        # Save raw
        output_path.write_bytes(raw_bytes)
        print(f"{size_mb:.1f}MB")


def date_to_key(d: date) -> str:
    return f"{OPTIONS_PREFIX}/{d.year}/{d.month:02d}/{d.isoformat()}.csv.gz"


def parse_args():
    p = argparse.ArgumentParser(
        description="Download Massive.com options flat files from S3"
    )
    p.add_argument("--year", type=int, help="Year to download (e.g., 2025)")
    p.add_argument("--month", type=int, help="Month to download (1-12)")
    p.add_argument("--date", type=str, help="Specific date (YYYY-MM-DD)")
    p.add_argument("--tickers", type=str, help="Comma-separated tickers to filter (e.g., SPY,AAPL,NVDA)")
    p.add_argument("--output", type=str, default=None, help="Output directory")
    p.add_argument("--list", action="store_true", help="List available files without downloading")
    return p.parse_args()


def main():
    args = parse_args()

    if not args.year and not args.date:
        print("Error: provide --year or --date")
        sys.exit(1)

    output_dir = Path(args.output) if args.output else DEFAULT_OUTPUT
    output_dir.mkdir(parents=True, exist_ok=True)

    tickers = None
    if args.tickers:
        tickers = set(t.strip().upper() for t in args.tickers.split(","))
        print(f"Filtering to tickers: {tickers}")

    client = get_s3_client()

    if args.date:
        # Single date
        d = date.fromisoformat(args.date)
        key = date_to_key(d)
        if args.list:
            print(key)
        else:
            print(f"Downloading {args.date} -> {output_dir}/")
            download_file(client, key, output_dir, tickers)
    else:
        # Year or year+month
        print(f"Listing files for {args.year}" + (f"-{args.month:02d}" if args.month else "") + " ...")
        keys = list_files(client, args.year, args.month)
        print(f"Found {len(keys)} files")

        if args.list:
            for k in keys:
                print(f"  {k}")
        else:
            print(f"Downloading to {output_dir}/")
            for i, key in enumerate(keys, 1):
                print(f"[{i}/{len(keys)}]", end="")
                download_file(client, key, output_dir, tickers)

    print("Done.")


if __name__ == "__main__":
    main()
