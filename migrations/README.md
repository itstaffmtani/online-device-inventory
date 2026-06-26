# migrations/ — migrasi skema database (yoyo-migrations)

Sumber kebenaran untuk perubahan skema SQLite **ke depan**. Tiap perubahan
skema = satu file `.sql` bernomor, dijalankan terurut, terlacak versinya di
tabel `_yoyo_migration`, dan bisa di-rollback.

## Kenapa ada ini
Dulu skema "disinkronkan" lewat kode tangan di `db.py::init_db()` (daftar
`ALTER ADD COLUMN` hardcoded). Itu rapuh: tanpa urutan, tanpa versi, tanpa
rollback. yoyo menggantikan itu untuk perubahan baru.

## Perintah (pakai wrapper `migrate.py` di root)
```bash
python migrate.py list       # status tiap migrasi
python migrate.py apply      # terapkan yang belum jalan
python migrate.py rollback   # mundur 1 migrasi terakhir
python migrate.py mark       # tandai applied TANPA run (baseline DB lama)
```
DB target otomatis = `config.DB_PATH` (env `DB_PATH`, default `data/inventory.db`).

## Menambah migrasi baru
1. Buat file `NNNN_deskripsi-singkat.sql` (nomor urut berikutnya), mis.
   `0002_tambah-kolom-warranty.sql`.
2. Tulis SQL maju di file utama. Untuk rollback, buat file pasangan
   `0002_tambah-kolom-warranty.rollback.sql` (opsional tapi disarankan).
3. `python migrate.py apply`.

Contoh menambah kolom:
```sql
-- 0002 — tambah kolom warranty_until ke submissions
ALTER TABLE submissions ADD COLUMN warranty_until TEXT;
```

> Catatan SQLite: `ALTER TABLE ... ADD COLUMN` tidak punya `IF NOT EXISTS`.
> Karena itu kolom baru HANYA boleh ditambah lewat migrasi yoyo (sekali jalan,
> terlacak) — jangan lagi menambah ke daftar di `db.py::init_db()`.

## Catatan produksi (penting, aman)
- `0001.initial-schema.sql` IDEMPOTEN (`CREATE TABLE IF NOT EXISTS`). Pada DB
  produksi yang skemanya sudah ada, `apply` aman jadi no-op. Alternatif paling
  bersih: `python migrate.py mark` sekali untuk membaselinekan, lalu pakai
  `apply` untuk migrasi berikutnya.
- **Selalu backup file DB sebelum `apply` di produksi.** `init_db()` juga sudah
  membuat `inventory.db.bak` otomatis saat start.
- `init_db()` di `app.py` masih jalan seperti biasa (startup tidak berubah).
  yoyo dipakai untuk evolusi skema berikutnya. Lihat catatan di `db.py`.
