# Deploy ke VPS Ubuntu (sub-path `/laptop-inventory`)

App dipasang di **`https://mtani.demosiapp.com/laptop-inventory`** karena root domain
sudah dipakai. nginx sudah terpasang & domain sudah mengarah ke IP VPS.

Stack: **gunicorn** (WSGI) di belakang **nginx** (reverse proxy + HTTPS yang sudah ada).
App sudah sadar sub-path lewat `ProxyFix` + header `X-Forwarded-Prefix`.

---

## 1. Ambil kode & buat virtualenv
```bash
sudo mkdir -p /var/www/laptop-inventory
sudo chown $USER:$USER /var/www/laptop-inventory
git clone <URL_REPO> /var/www/laptop-inventory
cd /var/www/laptop-inventory

python3 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt   # Flask, openpyxl, gunicorn
```

## 2. Konfigurasi (.env)
```bash
cp .env.example .env
# buat nilai rahasia:
python3 -c "import secrets; print(secrets.token_urlsafe(32))"   # untuk SECRET_KEY & SUBMIT_TOKEN
nano .env
```
Pastikan minimal:
```
ADMIN_PASSWORD=...
SUBMIT_TOKEN=...
FLASK_SECRET_KEY=...
SERVER_BASE_URL=https://mtani.demosiapp.com/laptop-inventory
DB_PATH=/var/www/laptop-inventory/data/inventory.db
```

## 3. Folder data + permission
`data/cpu_seed.csv` ikut repo (acuan PassMark). DB dibuat otomatis saat start.
```bash
mkdir -p data
sudo chown -R www-data:www-data /var/www/laptop-inventory/data
```
> Service jalan sebagai `www-data`, jadi folder `data/` wajib writable olehnya.

## 4. systemd service (gunicorn)
```bash
sudo cp deploy/laptop-inventory.service /etc/systemd/system/laptop-inventory.service
sudo systemctl daemon-reload
sudo systemctl enable --now laptop-inventory
systemctl status laptop-inventory --no-pager      # harus "active (running)"
curl -s -H "X-Forwarded-Prefix: /laptop-inventory" http://127.0.0.1:8080/ | head   # sanity check
```

## 5. nginx (tambah location ke server block yang sudah ada)
Buka konfigurasi server `mtani.demosiapp.com` (mis. `/etc/nginx/sites-available/...`)
dan **tempel isi `deploy/nginx-laptop-inventory.conf` ke dalam `server { ... }`** yang
sudah HTTPS. Lalu:
```bash
sudo nginx -t && sudo systemctl reload nginx
```

## 6. Verifikasi
- `https://mtani.demosiapp.com/laptop-inventory/` → halaman landing.
- Klik **Unduh untuk Windows** → dapat `Check-Laptop.bat` (cek isinya menunjuk ke
  `https://mtani.demosiapp.com/laptop-inventory`).
- Buka `/laptop-inventory/admin` → login dengan `ADMIN_PASSWORD`.
- Isi form via `/laptop-inventory/form` → submit → skor muncul → tampil di dashboard.

---

## Adopsi migrasi yoyo (SEKALI saja, saat update ke versi ini)
DB produksi sudah punya skema (dibuat `init_db()` lama). Cukup **baseline**-kan
sekali agar yoyo tahu skema sudah ada, tanpa menjalankan ulang apa-apa:
```bash
cd /var/www/laptop-inventory
git pull
./venv/bin/pip install -r requirements.txt          # ada yoyo-migrations baru
sudo cp data/inventory.db data/inventory.db.pre-yoyo.bak   # backup dulu
sudo -u www-data ./venv/bin/python migrate.py mark  # tandai 0001 "applied" (tanpa run)
sudo systemctl restart laptop-inventory
```

## Update versi berikutnya (rutin)
> Selalu pakai **`./venv/bin/python`** (di Ubuntu `python` tidak ada — adanya
> `python3`), dan jalankan sebagai **`www-data`** agar file DB tetap dimiliki service.
```bash
cd /var/www/laptop-inventory                              # sesuaikan path instalasi Anda
git pull
./venv/bin/pip install -r requirements.txt
sudo cp data/inventory.db data/inventory.db.bak           # backup sebelum migrasi
sudo -u www-data ./venv/bin/python migrate.py apply       # migrasi skema (bila ada)

# Migrasi DATA one-off (bila rilis menyertakannya — lihat catatan rilis di bawah).
# Skrip otomatis membaca env DB_PATH; muat .env dulu agar path DB prod terpakai:
set -a; . ./.env; set +a
sudo -u www-data -E ./venv/bin/python migrate_workgroups_2026_06.py

sudo systemctl restart laptop-inventory
```
Setelah restart: login `/admin/skoring` → **"Hitung ulang semua"** (agar skor lama
ikut parameter baru), lalu cek `/admin/report`.

### Rilis 2026-06 — model profil bersama & revisi kelompok
Sekali jalan saat update ke rilis ini. Tabel baru (`scoring_profiles`) & kolom
`profile_key` dibuat otomatis saat start, **tetapi** pembersihan data lama
(hapus kelompok `marketing`, tambah `mandor`, gabung Keuangan+Pengolahan Data,
hapus profil `olah_data`) **wajib** lewat skrip — `INSERT OR IGNORE` tak bisa
menghapus/mengubah baris lama:
```bash
cd /var/www/laptop-inventory
sudo cp data/inventory.db data/inventory.db.bak
set -a; . ./.env; set +a                                  # ambil DB_PATH dari .env
sudo -u www-data -E ./venv/bin/python migrate_workgroups_2026_06.py
sudo systemctl restart laptop-inventory
```
Skrip **idempoten** (aman diulang) & **hanya menyentuh tabel konfigurasi**
(`work_groups`/`scoring_profiles`) — `submissions`/`employees`/`devices` tidak
disentuh. Selesai → `/admin/skoring` → "Hitung ulang semua".

### Rilis 2026-06b — skor CPU akurat, export XLSX berformula, bulk edit
**Murni kode — tanpa migrasi skema/data, tanpa dependency baru.** Jalur rutin saja:
```bash
cd /var/www/laptop-inventory
git pull
./venv/bin/pip install -r requirements.txt          # tak ada dep baru; aman
sudo cp data/inventory.db data/inventory.db.bak
sudo systemctl restart laptop-inventory
```
Lalu lewat browser: `/admin/skoring` → **"Hitung ulang semua"** — **wajib**, karena di
sinilah perbaikan pencocokan PassMark CPU menurunkan ulang skor lama yang sempat
menggelembung (nama CPU generik dulu tercocok ke varian terkuat). Isi rilis:
- Pencocokan PassMark diperketat; nama tanpa nomor model -> diperkirakan dari thread.
- Export XLSX jadi 4 sheet (Parameter·Data & Perhitungan·Ringkasan·Per Karyawan),
  nilai dihitung di Python (selalu tampil; rumus openpyxl kosong di Protected View).
- Bulk edit penempatan dari dashboard (tab Laptop & Karyawan).
- Panah "Detail ->" tak lagi turun ke baris bawah.

## Troubleshooting
- **502 Bad Gateway** → gunicorn mati: `journalctl -u laptop-inventory -n 50 --no-pager`.
- **Link/aset salah arah (ke root, bukan sub-path)** → pastikan nginx mengirim
  `X-Forwarded-Prefix /laptop-inventory` dan `proxy_pass` diakhiri slash (`:8080/;`).
- **Skor CPU semua "diperkirakan"** → `data/cpu_seed.csv` hilang; pastikan ikut ter-commit
  & ada di server, lalu `sudo systemctl restart laptop-inventory`.
- **Tidak bisa simpan / DB error** → permission `data/`: `sudo chown -R www-data:www-data data`.
