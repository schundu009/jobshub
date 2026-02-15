#!/usr/bin/env python3
"""
Clean old jobs from the database.

This script deletes jobs older than a specified number of days,
along with their related records (interviews, notes, documents).

Usage:
    # Dry run (preview what will be deleted)
    python -m scripts.clean_old_jobs --days 7 --dry-run

    # Actually delete
    python -m scripts.clean_old_jobs --days 7

    # Via Railway
    railway run python -m scripts.clean_old_jobs --days 7
"""

import argparse
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta
from sqlalchemy import text
from database import engine


def clean_old_jobs(days: int = 7, dry_run: bool = True) -> dict:
    """
    Delete jobs older than the specified number of days.

    Args:
        days: Number of days. Jobs older than this will be deleted.
        dry_run: If True, only preview without deleting.

    Returns:
        Dictionary with counts of affected records.
    """
    cutoff_date = datetime.utcnow() - timedelta(days=days)

    results = {
        "cutoff_date": cutoff_date.isoformat(),
        "dry_run": dry_run,
        "jobs_count": 0,
        "interviews_count": 0,
        "notes_count": 0,
        "documents_count": 0,
    }

    with engine.connect() as conn:
        # Get job IDs to delete
        job_ids_result = conn.execute(text("""
            SELECT id, title, created_at
            FROM jobs
            WHERE created_at < :cutoff
            ORDER BY created_at
        """), {"cutoff": cutoff_date})

        jobs_to_delete = job_ids_result.fetchall()
        results["jobs_count"] = len(jobs_to_delete)

        if not jobs_to_delete:
            print(f"No jobs found older than {days} days (cutoff: {cutoff_date})")
            return results

        job_ids = [job[0] for job in jobs_to_delete]

        print(f"\nFound {len(jobs_to_delete)} jobs to delete:")
        for job in jobs_to_delete[:10]:  # Show first 10
            print(f"  - ID {job[0]}: {job[1][:50]}... (created: {job[2]})")
        if len(jobs_to_delete) > 10:
            print(f"  ... and {len(jobs_to_delete) - 10} more")

        # Count related records
        for table, id_col in [("interviews", "job_id"), ("notes", "job_id"), ("documents", "job_id")]:
            try:
                count_result = conn.execute(text(f"""
                    SELECT COUNT(*) FROM {table} WHERE {id_col} = ANY(:ids)
                """), {"ids": job_ids})
                results[f"{table}_count"] = count_result.scalar() or 0
            except Exception as e:
                print(f"  Note: Could not count {table}: {e}")
                results[f"{table}_count"] = 0

        print(f"\nRelated records to be deleted:")
        print(f"  - Interviews: {results['interviews_count']}")
        print(f"  - Notes: {results['notes_count']}")
        print(f"  - Documents: {results['documents_count']}")

        if dry_run:
            print("\n[DRY RUN] No records were deleted. Run without --dry-run to delete.")
            return results

        # Delete related records first (those without CASCADE)
        print("\nDeleting records...")

        for table in ["interviews", "notes", "documents"]:
            try:
                conn.execute(text(f"DELETE FROM {table} WHERE job_id = ANY(:ids)"), {"ids": job_ids})
                print(f"  Deleted from {table}")
            except Exception as e:
                print(f"  Warning: Could not delete from {table}: {e}")

        # Delete jobs (this will cascade to job_relevance_scores and application_submissions)
        conn.execute(text("DELETE FROM jobs WHERE id = ANY(:ids)"), {"ids": job_ids})
        print(f"  Deleted {len(job_ids)} jobs")

        conn.commit()
        print("\nCleanup completed successfully!")

    return results


def main():
    parser = argparse.ArgumentParser(description="Clean old jobs from the database")
    parser.add_argument("--days", type=int, default=7, help="Delete jobs older than this many days (default: 7)")
    parser.add_argument("--dry-run", action="store_true", help="Preview without deleting")

    args = parser.parse_args()

    print(f"Job Cleanup Script")
    print(f"==================")
    print(f"Database: {os.environ.get('DATABASE_URL', 'local').split('@')[-1] if '@' in os.environ.get('DATABASE_URL', '') else 'local'}")
    print(f"Cutoff: {args.days} days")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'DELETE'}")

    results = clean_old_jobs(days=args.days, dry_run=args.dry_run)

    print(f"\nSummary:")
    print(f"  Jobs: {results['jobs_count']}")
    print(f"  Interviews: {results['interviews_count']}")
    print(f"  Notes: {results['notes_count']}")
    print(f"  Documents: {results['documents_count']}")


if __name__ == "__main__":
    main()
