#!/usr/bin/env python3
"""Import options flat files (gzip CSV) into DuckDB.

Reads all .csv.gz files from app/data/flat_files/, parses OCC tickers,
converts timestamps, and inserts into the options table.

Usage:
    python import_flat_files.py                    # import all files
    python import_flat_files.py --dir /some/path   # custom directory
    python import_flat_files.py --stats            # show DB stats only
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.data.db import get_db, import_all_flat_files, import_flat_file, get_stats, close_db

DEFAULT_DIR = Path(__file__).parent / "app" / "data" / "flat_files"


def main():
    parser = argparse.ArgumentParser(description="Import options flat files into DuckDB")
    parser.add_argument("--dir", type=str, default=None, help="Directory with .csv.gz files")
    parser.add_argument("--file", type=str, default=None, help="Import a single .csv.gz file")
    parser.add_argument("--stats", action="store_true", help="Show DB stats and exit")
    args = parser.parse_args()

    if args.stats:
        stats = get_stats()
        print(f"Rows:       {stats['rows']:,}")
        print(f"Date range: {stats['date_range']}")
        print(f"Tickers:    {len(stats['tickers'])} unique")
        if stats['tickers']:
            print(f"            {', '.join(stats['tickers'][:20])}" +
                  ("..." if len(stats['tickers']) > 20 else ""))
        return

    if args.file:
        path = Path(args.file)
        if not path.exists():
            print(f"File not found: {path}")
            sys.exit(1)
        start = time.time()
        count = import_flat_file(path)
        elapsed = time.time() - start
        print(f"\nImported {count:,} rows in {elapsed:.1f}s")
    else:
        directory = Path(args.dir) if args.dir else DEFAULT_DIR
        if not directory.exists():
            print(f"Directory not found: {directory}")
            sys.exit(1)

        files = sorted(directory.glob("*.csv.gz"))
        if not files:
            print(f"No .csv.gz files in {directory}")
            sys.exit(1)

        print(f"Importing {len(files)} files from {directory}")
        start = time.time()
        total = import_all_flat_files(directory)
        elapsed = time.time() - start
        print(f"\nImported {total:,} rows in {elapsed:.1f}s ({total/max(elapsed,1):,.0f} rows/s)")

    print()
    stats = get_stats()
    print(f"DB total:   {stats['rows']:,} rows")
    print(f"Date range: {stats['date_range']}")
    print(f"Tickers:    {len(stats['tickers'])} unique")
    close_db()


if __name__ == "__main__":
    main()
