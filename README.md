# Syschecker Web

Aplikasi web untuk mendeteksi dan melaporkan spesifikasi hardware sistem komputer. Aplikasi ini membantu Anda mendapatkan informasi lengkap tentang perangkat, CPU, RAM, penyimpanan, dan GPU dengan mudah dalam format interaktif, CSV, atau PDF.

## 🎯 Fitur Utama

- **Deteksi Hardware Otomatis**: Menampilkan informasi lengkap tentang perangkat keras sistem
- **Web Interface**: Antarmuka web yang user-friendly dan responsif
- **Export ke CSV**: Ekspor laporan ke format CSV dengan mitigasi OWASP CSV Injection
- **Export ke PDF**: Ekspor laporan profesional ke format PDF
- **Multi-Platform**: Kompatibel dengan Windows, Linux, dan macOS
- **Keamanan**: Implementasi best practice keamanan OWASP

## 📋 Informasi yang Ditampilkan

### Sistem & Perangkat
- Merk/Model perangkat
- Sistem Operasi
- Arsitektur (32-bit/64-bit)

### CPU/Prosesor
- Model CPU
- Jumlah Core Fisik
- Jumlah Thread
- Kecepatan Prosesor

### Memori (RAM)
- Total RAM
- RAM yang Terpakai
- Persentase Penggunaan

### Penyimpanan (Disk)
- Tipe Media Penyimpanan Fisik
- Status Partisi Logis
- Kapasitas Total dan Sisa

### GPU
- Informasi Unit GPU

## 💻 Persyaratan Sistem

- **Python**: 3.7 atau lebih tinggi
- **OS**: Windows, Linux, atau macOS
- **RAM**: Minimal 512 MB
- **Koneksi Internet**: Hanya diperlukan untuk instalasi dependencies (pertama kali)

## 🔧 Dependensi Python

```
Flask==2.3.0
psutil==5.9.0
py-cpuinfo==9.0.0
fpdf==1.7.2
```

## 📦 Instalasi

### 1. Clone atau Download Project
```bash
# Jika menggunakan Git
git clone <repository-url>
cd syschecker-web

# Atau download ZIP dan ekstrak ke folder yang diinginkan
```

### 2. Buat Virtual Environment (Opsional tapi Direkomendasikan)

**Windows:**
```bash
python -m venv venv
venv\Scripts\activate
```

**Linux/macOS:**
```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

Atau install manual:
```bash
pip install Flask psutil py-cpuinfo fpdf
```

## 🚀 Menjalankan Aplikasi

### Cara 1: Menjalankan di Local Machine

**Windows:**
```bash
python app.py
```

**Linux/macOS:**
```bash
python3 app.py
```

Aplikasi akan berjalan di: **http://127.0.0.1:5000**

### Cara 2: Menjalankan dengan Konfigurasi Custom

Anda bisa memodifikasi `app.py` untuk mengubah:
- Port (default: 5000)
- Debug mode
- Host binding

Contoh:
```python
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
```

## 🌐 Menggunakan Aplikasi

### Via Web Browser

1. Buka browser (Chrome, Firefox, Edge, Safari, dll)
2. Kunjungi: `http://localhost:5000`
3. Halaman utama akan menampilkan semua informasi hardware

### Fitur Export

- **Export CSV**: Klik tombol "Export CSV" untuk mengunduh laporan dalam format CSV
- **Export PDF**: Klik tombol "Export PDF" untuk mengunduh laporan dalam format PDF

## 📁 Struktur Project

```
syschecker-web/
├── app.py                  # Main Flask application
├── hardware_service.py     # Service untuk deteksi hardware
├── requirements.txt        # Python dependencies
├── README.md              # File ini
└── templates/
    └── index.html         # Web interface template
```

## 🛠️ Troubleshooting

### Error: "Module not found"
**Solusi**: Pastikan semua dependencies sudah terinstall
```bash
pip install -r requirements.txt
```

### Error: "Port 5000 already in use"
**Solusi**: Gunakan port yang berbeda
```python
# Modifikasi di app.py
app.run(port=8000)  # Ganti dengan port lain
```

### Error pada Windows: "Cannot find wmic command"
**Solusi**: Jalankan aplikasi dengan administrator privilege atau gunakan PowerShell

### Error: "Permission denied" (Linux/macOS)
**Solusi**: Pastikan file punya executable permission
```bash
chmod +x app.py
```

## 🔒 Keamanan

Aplikasi ini menerapkan best practice keamanan:
- **CSV Injection Mitigation**: Sanitasi data yang diexport ke CSV
- **Input Validation**: Validasi data sebelum ditampilkan
- **Safe Subprocess Execution**: Menggunakan safe methods untuk system command execution

## 📝 Catatan

- Informasi hardware diambil secara real-time dari sistem
- Beberapa informasi memerlukan akses administrator (terutama di Windows)
- Laporan PDF akan dienkode dengan UTF-8 untuk mendukung karakter Indonesia

## 📄 Lisensi

Project ini dibuat untuk keperluan diagnostik sistem.

## 👨‍💻 Kontribusi

Untuk melaporkan bug atau mengusulkan fitur, silahkan buat issue di repository ini.

---

**Selamat menggunakan Syschecker Web!** 🚀
