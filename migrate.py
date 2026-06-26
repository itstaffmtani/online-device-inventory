#!/usr/bin/env python
"""migrate.py — jalankan migrasi skema SQLite via yoyo-migrations.

Pembungkus tipis agar tak perlu mengetik connection string. Otomatis pakai
`config.DB_PATH` (env DB_PATH atau default data/inventory.db), sama seperti app.

Pemakaian:
    python migrate.py apply      # terapkan semua migrasi yang belum jalan
    python migrate.py list       # lihat status tiap migrasi (applied / belum)
    python migrate.py rollback   # mundur 1 migrasi terakhir
    python migrate.py mark       # tandai semua "applied" TANPA menjalankan
                                 #   (untuk membaselinekan DB lama yang skemanya
                                 #    sudah ada — aman karena 0001 idempoten)

File migrasi ada di folder migrations/ (lihat migrations/README.md).
Sebelum apply di produksi: backup file DB dulu.
"""

import os
import sys

from yoyo import get_backend, read_migrations

from config import config

MIGRATIONS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "migrations")


def _backend_and_migrations():
    db_path = config.DB_PATH
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    # yoyo butuh path absolut bergaya URI; pakai 4 slash untuk path absolut.
    backend = get_backend(f"sqlite:///{db_path}")
    migrations = read_migrations(MIGRATIONS_DIR)
    return backend, migrations


def cmd_apply():
    backend, migrations = _backend_and_migrations()
    with backend.lock():
        to_apply = backend.to_apply(migrations)
        if not to_apply:
            print("Tidak ada migrasi baru. Skema sudah mutakhir.")
            return
        for m in to_apply:
            print(f"apply  {m.id}")
        backend.apply_migrations(to_apply)
    print("Selesai.")


def cmd_rollback():
    backend, migrations = _backend_and_migrations()
    with backend.lock():
        to_rollback = backend.to_rollback(migrations)
        if not to_rollback:
            print("Tidak ada migrasi untuk dimundurkan.")
            return
        last = to_rollback[:1]  # mundur 1 langkah saja, hati-hati
        for m in last:
            print(f"rollback  {m.id}")
        backend.rollback_migrations(last)
    print("Selesai.")


def cmd_mark():
    backend, migrations = _backend_and_migrations()
    with backend.lock():
        to_apply = backend.to_apply(migrations)
        for m in to_apply:
            print(f"mark applied (tanpa run)  {m.id}")
        backend.mark_migrations(to_apply)
    print("Selesai. DB dibaselinekan.")


def cmd_list():
    backend, migrations = _backend_and_migrations()
    applied = {m.id for m in backend.to_rollback(migrations)}
    for m in migrations:
        flag = "[x] applied" if m.id in applied else "[ ] belum"
        print(f"{flag}  {m.id}")


def main(argv):
    cmds = {
        "apply": cmd_apply,
        "rollback": cmd_rollback,
        "mark": cmd_mark,
        "list": cmd_list,
    }
    if len(argv) != 2 or argv[1] not in cmds:
        print(__doc__)
        print(f"DB: {config.DB_PATH}")
        return 1
    cmds[argv[1]]()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
