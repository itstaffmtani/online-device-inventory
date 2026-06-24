# Brief Aturan Penilaian Kelayakan (Scoring)

Dokumen ini adalah **sumber kebenaran untuk manusia**. Implementasi di
`scoring.py` harus mengikuti angka di sini. Semua ambang sengaja ditaruh sebagai
konstanta agar mudah dikalibrasi setelah lihat data nyata.

Dasar acuan beban kerja per kelompok = PDF *"Rekomendasi Spesifikasi Laptop
Berdasarkan Kelompok Karyawan"* (Tim IT MTani, Juni 2026).

---

## 0. Keluaran yang dihasilkan
Untuk tiap laptop (submission terbaru):
- **Skor Spek** (0-100) — kualitas hardware terhadap kebutuhan perannya.
- **Skor Beban** (0-100) — ketahanan terhadap beban kerja nyata (RAM pressure).
- **Skor Total** (0-100) — headline = `round(0.7 * Skor Spek + 0.3 * Skor Beban)`.
- **Status** — `Layak` / `Upgrade` / `Ganti` (+ daftar alasan).
- **Estimasi Tahun Pensiun** (EOL year).

---

## 1. Profil kebutuhan per kelompok kerja
`CPU floor/ideal` = skor **PassMark multi-thread**. `RAM` dalam GB.
Angka PassMark di bawah adalah **anchor perkiraan** dari CPU acuan PDF —
**verifikasi & seed dari cpubenchmark.net** saat mengisi tabel `cpu_benchmarks`.

| Kelompok | CPU floor | CPU ideal | RAM min | RAM ideal | CPU acuan (PDF) |
|---|---:|---:|---:|---:|---|
| `field` | 8.000 | 16.000 | 8 | 16 | Ryzen 3 7320U → Ryzen 5 7530U |
| `admin` | 12.000 | 18.000 | 8 | 16 | i3-1315U → i5-1335U |
| `finance` | 17.000 | 26.000 | 16 | 32 | i5-1335U → Ultra 5 / Ryzen 7 |
| `data_processing` | 17.000 | 26.000 | 16 | 32 | i5-1335U → Ultra 5 / Ryzen 7 |
| `management` | 15.000 | 24.000 | 16 | 16 | i5/Ryzen 5 → Ultra 5/Ryzen 7 |
| `it` | 17.000 | 24.000 | 16 | 32 | Ryzen 5 7535HS → Ryzen 7 7735HS / Ultra 7 |

> Catatan: `finance` & `data_processing` dasarnya sama (Excel/data berat), tetap
> dipisah agar laporan bisa membedakan. `management` RAM ideal 16 (32 hanya bila
> ada kebutuhan data khusus) — bobot baterai/portabilitas lebih tinggi (§3).

---

## 2. Komponen Skor Spek (0-100)
Tiap komponen dihitung 0-100, lalu dijumlah berbobot.

### 2a. CPU points
```
ratio = cpu_passmark / profil.cpu_ideal
cpu_points = clamp(round(100 * ratio), 0, 100)
```
(Di skor ideal → 100; setengahnya → ~50.) Bila CPU tak ada di tabel → lihat §6 fallback.

### 2b. RAM points
```
ratio = ram_gb / profil.ram_ideal
ram_points = clamp(round(100 * ratio), 0, 100)
```

### 2c. Storage points (ambil yang terbaik terpasang)
| Kondisi | Poin |
|---|---:|
| Ada SSD NVMe | 100 |
| Ada SSD SATA/M.2 | 85 |
| HDD saja (tanpa SSD) | 25 |
| Tidak terdeteksi | 50 (netral) |

### 2d. Battery points
```
health = battery_wh_full / battery_wh_design * 100   (bila data ada)
battery_points = clamp(round(health), 0, 100)
```
- Bila tak ada baterai (PC desktop) atau data kosong → **netral**, komponen ini
  dikeluarkan dari rata-rata berbobot (bobotnya dibagikan ke komponen lain).

### 2e. Bobot komponen (default)
| Komponen | Bobot umum | Bobot `management` |
|---|---:|---:|
| CPU | 35% | 30% |
| RAM | 30% | 25% |
| Storage | 20% | 20% |
| Battery | 15% | 25% |

```
Skor Spek = Σ(poin_komponen * bobot) / Σ(bobot komponen yang dipakai)
```

---

## 3. Skor Beban (0-100) — "layak secara load"
Mengukur apakah laptop sanggup menahan beban kerja nyata. Dua faktor:

### 3a. Tekanan RAM (snapshot `ram_usage_pct`)
| ram_usage_pct saat capture | Poin tekanan |
|---|---:|
| ≤ 60% | 100 |
| 60–80% | 100 → 70 (linear) |
| 80–90% | 70 → 40 (linear) |
| > 90% | 40 → 0 (linear, mepet penuh) |
Bila `ram_usage_pct` kosong → netral 100.

### 3b. Kecukupan RAM terhadap peran
```
ram_adequacy = clamp(round(100 * ram_gb / profil.ram_min), 0, 100)
```
(Di bawah RAM minimum kelompok → turun tajam.)

```
Skor Beban = round(0.5 * poin_tekanan + 0.5 * ram_adequacy)
```

> Catatan kejujuran: snapshot sekali itu sinyal lemah. Ia menurunkan skor bila
> jelas mepet, tapi tidak dijadikan satu-satunya penentu. Penentu utama tetap
> spek vs kebutuhan peran.

---

## 4. Status (Layak / Upgrade / Ganti)
Tentukan dari **Skor Total**, lalu terapkan **aturan paksa** yang bisa menurunkan
status (override) beserta alasannya.

### 4a. Dari skor
| Skor Total | Status |
|---|---|
| 70–100 | `Layak` |
| 45–69 | `Upgrade` |
| 0–44 | `Ganti` |

### 4b. Aturan paksa (override + alasan ditambahkan ke `status_reasons`)
- `ram_gb < profil.ram_min` → minimal `Upgrade`, alasan: *"RAM {x}GB di bawah minimum {min}GB untuk kelompok {grup} — tambah RAM"*.
- HDD saja (tidak ada SSD) → minimal `Upgrade`, alasan: *"Belum SSD — ganti ke SSD"*.
- `cpu_passmark < profil.cpu_floor` → minimal `Upgrade`; bila `< 0.6 * cpu_floor` → `Ganti`, alasan: *"CPU di bawah batas bawah kelompok"*.
- `os_free_gb < 20` → tambah alasan (tidak menaikkan status): *"Penyimpanan OS hampir penuh"*.

### 4c. Catatan komponen (bukan status laptop, tapi flag terpisah)
- `battery_health < 60%` → flag *"Baterai sehat <60% — pertimbangkan ganti baterai"*.
  (Ganti baterai ≠ ganti laptop, jadi tidak otomatis bikin status `Ganti`.)
- `physical_condition = poor` atau ada `issues` → tampilkan sebagai catatan
  perawatan, terpisah dari skor kelayakan teknis.

---

## 5. Estimasi Tahun Pensiun (EOL)
Asumsi masa pakai dasar **5 tahun** sejak pembelian, disesuaikan kualitas spek:
```
masa_pakai = 5
if Skor Spek >= 80: masa_pakai += 1     # spek kuat, awet lebih lama
if Skor Spek <  55: masa_pakai -= 1     # spek pas-pasan, pensiun lebih cepat
eol_year = purchase_year + masa_pakai
```
- Bila `purchase_year` kosong → EOL tidak dihitung (tampilkan "—", minta lengkapi).
- Bila `status = Ganti` atau `eol_year <= tahun_sekarang` → tampilkan
  **"Sudah waktunya diganti"**.
- `tahun_sekarang` diambil dari server saat scoring (jangan hardcode).

---

## 6. Fallback bila CPU tak ada di tabel benchmark
1. Normalisasi & fuzzy match dulu (lowercase, buang "(R)", "(TM)", "CPU @", spasi ganda).
2. Bila tetap gagal:
   - Tebak kasar dari `cpu_cores`/`cpu_threads` → estimasi PassMark kasar
     (mis. `passmark ≈ threads * 1800`), beri flag `cpu_estimasi=true`.
   - Tandai di `status_reasons`: *"Skor CPU diperkirakan (model tak dikenali) —
     verifikasi manual"*.
3. Catat model yang gagal ke log agar tabel `cpu_benchmarks` bisa dilengkapi.

---

## 7. Contoh perhitungan (ilustrasi)
**Laptop admin, Ryzen 5 7530U (PassMark ~16.000), RAM 8GB, SSD NVMe, baterai
health 70%, RAM usage 75%, beli 2022.**
Profil `admin`: cpu_ideal 18.000, ram_ideal 16, ram_min 8.

- CPU points = 100*16000/18000 = **89**
- RAM points = 100*8/16 = **50**
- Storage = **100** (NVMe)
- Battery = **70**
- Skor Spek = (89*.35 + 50*.30 + 100*.20 + 70*.15)/1.0 = 31.15+15+20+10.5 = **77**
- Tekanan RAM (75%) = 100 - (75-60)/(80-60)*30 = 100-22.5 = **77.5**
- RAM adequacy = 100*8/8 = **100**
- Skor Beban = round(.5*77.5 + .5*100) = **89**
- Skor Total = round(.7*77 + .3*89) = round(53.9+26.7) = **81 → Layak**
- Override: ram_gb(8) == ram_min(8) → tidak kena. SSD ada → aman.
- EOL: Skor Spek 77 (tak ≥80, tak <55) → masa_pakai 5 → **2027**.

Hasil: **Skor 81 · Layak · pensiun ~2027**, catatan baterai 70% (masih wajar).

---

## 8. Yang harus dikalibrasi setelah data nyata masuk
- Anchor PassMark per kelompok (§1) — sesuaikan dgn distribusi CPU yang benar-benar dipakai.
- Bobot komponen (§2e) — bila ternyata RAM lebih krusial dari perkiraan.
- Ambang status (§4a) — agar proporsi Layak/Upgrade/Ganti masuk akal.
- Masa pakai dasar EOL (§5) — sesuai kebijakan aset perusahaan.
