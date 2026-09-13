"""Apply numbered SQL migrations, once each, in filename order.

Deliberately not Alembic: this project has one schema, no branching history, and
adding a migration framework would be more machinery than the problem needs.
"""
import os
import sys

from db.connection import connect

TRACKING = """
create table if not exists schema_migrations (
    filename   text primary key,
    applied_at timestamptz not null default now()
)
"""


def apply_all(conn, migrations_dir):
    conn.execute(TRACKING)
    applied = {r[0] for r in conn.execute(
        "select filename from schema_migrations").fetchall()}

    ran = []
    for filename in sorted(os.listdir(migrations_dir)):
        if not filename.endswith(".sql") or filename in applied:
            continue
        with open(os.path.join(migrations_dir, filename)) as handle:
            conn.execute(handle.read())
        conn.execute("insert into schema_migrations (filename) values (%s)",
                     (filename,))
        ran.append(filename)

    conn.commit()
    return ran


if __name__ == "__main__":
    with connect() as connection:
        for name in apply_all(connection, "db/migrations"):
            print(f"applied {name}")
