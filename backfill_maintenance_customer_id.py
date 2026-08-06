"""
backfill_maintenance_customer_id.py
------------------------------------
One-time migration script — safe to run multiple times (idempotent).

For every Maintenance row where customer_id IS NULL, this script looks up
the machine's assigned_customer_id and fills it in.

Run from the project root:
    python backfill_maintenance_customer_id.py

In production (if running via gunicorn/waitress), stop the server first,
run the script, then restart:
    python backfill_maintenance_customer_id.py && <start server command>
"""

import sys
from app import create_app
from extensions import db
from models.maintenance import Maintenance
from models.machine import Machine


def backfill():
    app = create_app()
    with app.app_context():
        # Find all maintenance rows with no customer_id
        orphaned = (
            Maintenance.query
            .filter(Maintenance.customer_id.is_(None))
            .all()
        )

        print(f"Found {len(orphaned)} maintenance record(s) with NULL customer_id.")

        updated = 0
        skipped = 0

        for record in orphaned:
            machine = db.session.get(Machine, record.machine_id)
            if machine and machine.assigned_customer_id:
                record.customer_id = machine.assigned_customer_id
                updated += 1
                print(
                    f"  [UPDATE] service_id={record.service_id} | "
                    f"machine_id={record.machine_id} | "
                    f"customer_id -> {machine.assigned_customer_id} | "
                    f"date={record.service_date}"
                )
            else:
                skipped += 1
                print(
                    f"  [SKIP]   service_id={record.service_id} | "
                    f"machine_id={record.machine_id} — "
                    f"machine has no assigned customer"
                )

        if updated:
            db.session.commit()
            print(f"\nDone. {updated} record(s) updated, {skipped} skipped.")
        else:
            print("\nNothing to update.")


if __name__ == '__main__':
    backfill()
