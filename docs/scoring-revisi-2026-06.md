# Revisi Scoring — Standar Frugal + Kepemilikan (2026-06)

> **STATUS: SUDAH DIEKSEKUSI (2026-06).** Seluruh §D diterapkan ke kode
> (`scoring.py`, `scoring_config.py`), data CPU dibangun ulang dari PassMark resmi,
> DB dimigrasi (`migrate_frugal_2026_06.py`) & semua submission dihitung ulang.
> Keputusan final sudah dipindah ke **sumber kebenaran** [scoring.md](scoring.md).
> Dokumen ini kini menjadi **arsip** latar/keputusan revisi (checklist §D tercentang).

Pemicu: data CPU baru yang lebih akurat di
[`data/passmark_single_cpu_intel_amd.csv`](../data/passmark_single_cpu_intel_amd.csv)
(nilai di `cpu_seed.csv` lama tidak sesuai — lihat §C).

---

## A. Isi revisi yang diajukan (dirapikan)

### A.1 Ambang status & EOL
- **Layak** 70–100 · **Upgrade** 35–69 · **Ganti** 0–34.
- Masa pakai EOL: **rata 5 tahun** (keputusan 2026-06: buang penyesuaian ±1 by
  spek — lihat §D.5). Estimasi planning saja, tak memengaruhi skor/status.

### A.2 Formula utama (tidak berubah)
- `Skor Total = round(0.7 * Skor Spek + 0.3 * Skor Beban)`.

### A.3 Skor Spek (0–100)
- **CPU points** = `clamp(round(100 * cpu_passmark / profil.cpu_ideal), 0, 100)`.
- **RAM points** = `clamp(round(100 * ram_gb / profil.ram_ideal), 0, 100)`.
- **Storage points**: NVMe 100 · SSD/M.2 85 · HDD 25, dikali faktor kesehatan
  disk `clamp(disk_health_pct/100, 0.5, 1.0)`.
- **Battery points** = `clamp(round(100 * battery_wh_full / battery_wh_design), 0, 100)`;
  bila tak ada baterai → dikeluarkan dari rata-rata berbobot.
- **Skor Spek** = rata-rata **berbobot per kelompok** (`W_*` di §A.6).

### A.4 Skor Beban (0–100)
- **Tekanan pemakaian** = rata-rata `ram_usage_pct` & `cpu_usage_pct`; **100 bila
  ≤ 60%, turun LINIER ke 0 saat mendekati 100%** (keputusan 2026-06: pakai linier,
  ganti formula piecewise lama — lihat §D.5).
- **Kecukupan RAM** = `clamp(round(100 * ram_gb / profil.ram_min), 0, 100)`.
- **Skor Beban** = `round(0.5 * Tekanan + 0.5 * Kecukupan RAM)`.

### A.5 Override & kepemilikan (BARU)
- **A. Penyimpanan**
  - `os_free_gb / os_total_gb < 0.15` → **Skor Beban −10**, alasan: *"Sisa
    penyimpanan < 15%, performa sistem menurun drastis. Segera bersihkan ruang
    penyimpanan."*
  - `disk_health_pct < 60` → alasan: *"Kesehatan disk menurun ({x}%), risiko data
    korup/hilang."*
- **B. Laptop personal** (`laptop_status = personal`)
  - `eol_year` → **NULL** (aset pribadi tak disusutkan perusahaan).
  - **Dikecualikan** dari `suggest_placement` (tak ditukar-silang antar karyawan).
  - Bila hasil **Upgrade/Ganti** → override saran: *"Performa aset pribadi
    menghambat produktivitas. Sediakan inventaris kantor (Rekomendasi teknis:
    [Tambah RAM/SSD])."*
- **C. Proteksi rotasi VIP** — kelompok **Manajemen** dikunci dari query rotasi ke
  bawah (`suggest_placement` tak pernah menyarankan laptop GM ditarik untuk staf).

### A.6 Profil kelompok (Standar Frugal) — seed `work_groups`
Target operasional umum = setara **Intel Core i3 Gen 12 / Ryzen 3** (PassMark
≈ 12.000); divisi teknis berat (IT/Keuangan/Data) ≥ 16.000.

| Kelompok | CPU floor | CPU ideal | RAM min | RAM ideal | W_CPU | W_RAM | W_Sto | W_Bat |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Lapangan | 6.000 | 12.000 | 8 | 16 | 0.30 | 0.30 | 0.20 | 0.20 |
| Administrasi | 6.000 | 12.000 | 8 | 16 | 0.30 | 0.30 | 0.20 | 0.20 |
| HR/GA | 6.000 | 12.000 | 8 | 16 | 0.30 | 0.30 | 0.20 | 0.20 |
| Marketing | 6.000 | 12.000 | 8 | 16 | 0.30 | 0.30 | 0.20 | 0.20 |
| Manajemen | 8.000 | 14.000 | 8 | 16 | 0.30 | 0.25 | 0.20 | 0.25 |
| Keuangan | 10.000 | 16.000 | 8 | 16 | 0.30 | 0.40 | 0.10 | 0.20 |
| Pengolahan Data | 10.000 | 16.000 | 8 | 16 | 0.30 | 0.40 | 0.15 | 0.15 |
| Design/Kreatif | 10.000 | 16.000 | 8 | 16 | 0.35 | 0.35 | 0.15 | 0.15 |
| IT | 14.000 | 22.000 | 16 | 32 | 0.40 | 0.35 | 0.15 | 0.10 |

Tiap baris `W_*` **wajib berjumlah 1.0** (sudah diverifikasi: semua = 1.00).

> Keputusan 2026-06: **Lapangan = Administrasi** (profil & bobot identik). Tabel di
> atas sudah disesuaikan — penekanan baterai 0.30 yang sebelumnya khas Lapangan
> dilepas. Bila kelak baterai field terbukti penting, kembalikan W_Bat 0.30.

---

## B. Review terhadap implementasi sekarang

Data model **sudah mendukung** semua perubahan ini: tabel `work_groups` punya
kolom `w_cpu..w_battery` per baris; `submissions` punya `laptop_status`
(enum `office_inventory`/`personal`), `os_total_gb`, `os_free_gb`, `cpu_usage_pct`.
→ **Tidak perlu migrasi skema.** Yang berubah: nilai seed + logika di `scoring.py`.

### B.1 Beda nilai vs `scoring_config.py` saat ini
| Param | Sekarang | Revisi | Catatan |
|---|---|---|---|
| `status_upgrade_min` | **45** | **35** | Pita Ganti menyempit (lebih longgar). |
| field/Lapangan ideal | 16.000 | 12.000 | Disamakan ke Administrasi (floor 8.000→6.000). |
| admin ideal | 18.000 | 12.000 | Floor 12.000→6.000. |
| finance ideal | 26.000 | 16.000 | Floor 17.000→10.000. RAM ideal 32→16. |
| data_processing ideal | 26.000 | 16.000 | RAM ideal 32→16. |
| management ideal | 24.000 | 14.000 | Floor 15.000→8.000. |
| it ideal | 24.000 | 22.000 | Floor 17.000→14.000. RAM ideal tetap 32. |
| marketing/hr/design | placeholder | nilai pasti | Naik dari `is_builtin=0` placeholder. |
| Bobot `W_*` | hanya `management` beda | **per kelompok** | Semua kelompok kini punya bobot khas. |

> Arah revisi = **frugal**: target ideal turun drastis (efisiensi budget), pita
> Ganti menyempit. Banyak laptop yang kini "Upgrade/Ganti" akan naik jadi
> "Layak". **Wajib jalankan "Hitung ulang semua"** setelah seed baru.

### B.2 Beda logika vs `scoring.py` / `scoring.md`
1. **Tekanan pemakaian** — revisi pakai 1 ramp linier (≤60%→100, 100%→0) atas
   rata-rata RAM+CPU. Implementasi sekarang ([scoring.md](scoring.md) §3a)
   **piecewise per tier** dan ambang CPU sedikit lebih longgar dari RAM.
   → **DIPUTUSKAN (2026-06): linier** (lebih mudah dijelaskan; piecewise dibuang).
2. **Penalti OS storage** — sekarang `os_free_gb < 20` (GB absolut) → **hanya
   alasan**, skor tak berubah. Revisi: **rasio** `< 0.15` → **−10 Skor Beban**.
   → Ganti ke berbasis rasio + benar-benar memotong skor.
3. **Kepemilikan personal** — `scoring.py` **belum** memperlakukan
   `laptop_status = personal` secara khusus (eol/rotasi/teks saran). **Logika baru.**
4. **Proteksi rotasi Manajemen** — `suggest_placement` belum mengunci VIP.
   **Logika baru.**
5. **EOL ±1 tahun by spek** — [scoring.md](scoring.md) §5 menyesuaikan masa pakai
   (+1 bila Skor Spek ≥80, −1 bila <55).
   → **DIPUTUSKAN (2026-06): ratakan 5 tahun** (buang ±1 — fitur minor, low-stakes).
6. **Storage "tak terdeteksi → 50 netral"** & flag-flag §9 scoring.md (OS support,
   Win11, headroom RAM) tidak disinggung revisi → **dipertahankan apa adanya**.

### B.3 Hal yang TIDAK berubah (aman)
Blend 0.7/0.3 · EOL dasar 5 tahun · rumus CPU/RAM/Storage/Battery points · faktor
kesehatan disk (min 0.5) · arsitektur data-driven (`work_groups`/`scoring_settings`).

---

## C. Data CPU baru (pemicu)

- `data/cpu_seed.csv` (185 baris): **~12 baris teratas terverifikasi** dari
  cpubenchmark.net (akurat), sisanya **"seed massal 2026-06" = tebakan** yang
  menyimpang dari PassMark asli → inilah yang "tidak sesuai".
- `data/passmark_single_cpu_intel_amd.csv` (**4.550 baris**): dataset otoritatif
  penuh Intel+AMD. Kolom: `CPU Name, Brand, CPU Mark, Rank, CPU Value, Price`.
- ⚠️ **Penting (nama file menyesatkan):** meski bernama `…_single_…`, kolom
  **`CPU Mark` (kolom 3) = nilai MULTI-thread** (persis yang dipakai
  `cpu_benchmarks.passmark_multi` & scoring). Kolom 4 = **Rank global**, *bukan*
  single-thread. File ini **tidak** memuat angka single-thread.
- Spot-check vs seed lama (selisih < 0.5%, valid): 7530U 15101→**15058** ·
  i5-1335U 13898→**13897** · Ultra 7 155H 24572→**24551** · 7735HS 22332→**22328**.
- ⚠️ CSV baru **tidak punya** kolom `cores` & `release_year`. Rebuild murni akan
  mengosongkan keduanya → **merge**, bukan replace (pertahankan cores/year dari
  baris lama bila ada; cores dipakai fallback PassMark di [scoring.md](scoring.md) §6).

---

## D. TODO (eksekusi nanti)

### D.1 Data CPU
- [x] **Skrip rebuild** `cpu_seed.csv` dari `passmark_single_cpu_intel_amd.csv`:
      map `CPU Name`→`cpu_key` (lower, normalisasi), `CPU Mark`→`passmark_multi`;
      `passmark_single` dikosongkan; `source = "PassMark (passmark_single_cpu_intel_amd.csv)"`.
- [x] **Merge, bukan timpa:** pertahankan `cores`/`release_year` dari baris
      `cpu_seed.csv` lama yang sudah punya; sisanya NULL.
- [x] Jalankan `python seed_cpu.py` (UPSERT idempoten) lalu verifikasi jumlah baris.
- [x] Buang/timpa baris "seed massal 2026-06" yang tertebak.

### D.2 Seed parameter scoring (`scoring_config.py`)
- [x] Update `_DEFAULT_GROUPS`: cpu_floor/ideal, ram_min/ideal, **bobot per
      kelompok** sesuai tabel §A.6 (field, admin, finance, data_processing,
      management, it, marketing, design, hr; aktifkan hr/marketing/design).
- [x] Tambah/selaraskan kelompok **HR/GA** (key `hr`) & label sesuai §A.6.
- [x] Ubah `_DEFAULT_SETTINGS["status_upgrade_min"]` 45 → **35**.
- [x] Catatan migrasi: `INSERT OR IGNORE` **tidak menimpa** baris yang sudah ada di
      DB. Siapkan jalur update (UI `/admin/skoring` atau skrip re-seed paksa) +
      **"Hitung ulang semua"** agar parameter baru benar-benar terpakai.

### D.3 Logika `scoring.py`
- [x] **Penalti OS storage** berbasis rasio: `os_free_gb/os_total_gb < 0.15` →
      `Skor Beban −10` + alasan (ganti aturan `< 20 GB` lama).
- [x] **Kepemilikan personal** (`laptop_status == "personal"`): `eol_year=None`;
      kecualikan dari `suggest_placement`; override teks saran saat Upgrade/Ganti.
- [x] **Proteksi rotasi Manajemen** di `suggest_placement` (VIP tak ditarik ke bawah).
- [x] **Tekanan pemakaian → linier** (keputusan 2026-06): ganti formula piecewise
      [scoring.md](scoring.md) §3a dengan 1 ramp linier (≤60%→100, 100%→0).
- [x] **EOL → rata 5 tahun** (keputusan 2026-06): hapus penyesuaian ±1 by Skor Spek
      di [scoring.md](scoring.md) §5 & kode.
- [x] **JANGAN buang flag perawatan** saat menyalin dari revisi (revisi hanya
      sebut *battery points*, tak sebut flag-flag ini): pertahankan **"ganti
      baterai"** ([scoring.py:472](../scoring.py#L472), `< 60%`), kesehatan disk,
      OS support, Win11, headroom RAM ([scoring.md](scoring.md) §9). Baterai soak =
      saran ganti baterai, **bukan** otomatis status "Ganti".
- [x] Perbarui self-test/contoh angka di `scoring.py` & [scoring.md](scoring.md) §7
      mengikuti profil + ambang baru.

### D.4 Dokumentasi
- [x] Setelah disetujui & dieksekusi: pindahkan keputusan final ke
      [scoring.md](scoring.md) (sumber kebenaran), perbarui §1/§2e/§3a/§4a/§5/§10.
- [x] Sinkronkan label kelompok di [schema.dbml](schema.dbml) bila ada penambahan.

### D.5 Keputusan (2026-06) — sudah final
1. ✅ Tekanan pemakaian → **linier** (buang piecewise).
2. ✅ EOL → **rata 5 tahun** (buang penyesuaian ±1 by Skor Spek).
3. ✅ Profil **Lapangan = Administrasi** (cpu 6.000/12.000, ram 8/16, bobot
   .30/.30/.20/.20). Penekanan baterai 0.30 dilepas.
