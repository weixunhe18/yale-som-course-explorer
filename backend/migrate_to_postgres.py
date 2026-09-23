"""Copy the local SQLite database into Supabase Postgres.

Run once, after creating the Supabase project and before the first deploy:

    cd backend
    DATABASE_URL='postgresql://...' ./.venv/bin/python migrate_to_postgres.py

Reads ``data/yale_som.db`` directly (never through ``DATABASE_URL``) and writes
to whatever ``DATABASE_URL`` points at. Re-running is safe: the script refuses to
touch a target that already has courses unless ``--replace`` is passed.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

# Load .env before importing db, which reads DATABASE_URL at import time.
_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / ".env")
load_dotenv(_ROOT.parent / ".env")

from sqlalchemy import create_engine, func, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from db import Base, Chat, Course, User, SQLITE_PATH, database_url  # noqa: E402

BATCH = 500


def _target_engine():
    url = database_url()
    if url.startswith("sqlite"):
        sys.exit(
            "DATABASE_URL is not set, so the target would be the same SQLite file.\n"
            "Set it to your Supabase connection string and run again."
        )
    return create_engine(url, pool_pre_ping=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Delete existing courses in the target first.",
    )
    args = parser.parse_args()

    if not SQLITE_PATH.exists():
        sys.exit(f"Source database not found: {SQLITE_PATH}")

    source = create_engine(f"sqlite:///{SQLITE_PATH}")
    target = _target_engine()

    # Create courses/users/chats in Postgres. create_all skips what exists.
    Base.metadata.create_all(target)
    print(f"tables ready on {target.url.host or target.url.database}")

    with Session(source) as src, Session(target) as dst:
        existing = dst.scalar(select(func.count()).select_from(Course)) or 0
        if existing and not args.replace:
            sys.exit(
                f"Target already has {existing} courses. "
                "Re-run with --replace to overwrite them."
            )
        if existing:
            dst.query(Course).delete()
            dst.commit()
            print(f"cleared {existing} existing courses")

        rows = src.scalars(select(Course).order_by(Course.id)).all()
        for start in range(0, len(rows), BATCH):
            chunk = rows[start : start + BATCH]
            dst.bulk_insert_mappings(
                Course,
                [
                    {
                        c.name: getattr(row, c.name)
                        for c in Course.__table__.columns
                    }
                    for row in chunk
                ],
            )
            dst.commit()
            print(f"  courses {start + len(chunk)}/{len(rows)}")

        # Postgres SERIAL keeps its own counter; after inserting explicit ids it
        # still points at 1, so the next insert would collide. Fast-forward it.
        dst.execute(
            func.setval(
                func.pg_get_serial_sequence("courses", "id"),
                max((r.id for r in rows), default=1),
            )
        )
        dst.commit()

        users = src.scalars(select(User)).all()
        chats = src.scalars(select(Chat)).all()
        print(
            f"\nlocal accounts not copied: {len(users)} users, {len(chats)} messages "
            "(sign up again against the deployed app)"
        )

    print(f"\ndone — {len(rows)} courses now in Postgres")


if __name__ == "__main__":
    main()
