from flask import Flask, render_template, make_response, request, jsonify
from hardware_service import HardwareDetector
import csv
import io
from fpdf import FPDF

app = Flask(__name__)
detector = HardwareDetector()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/diagnostik')
def api_diagnostik():
    hw_data = detector.get_all_info()
    return jsonify(hw_data)

@app.route('/export/csv')
def export_csv():
    # Tetap panggil detector saat proses cetak/ekspor
    hw_data = detector.get_all_info()
    
    nama = request.args.get('nama', 'N/A')
    jabatan = request.args.get('jabatan', 'N/A')
    perusahaan = request.args.get('perusahaan', 'N/A')
    penempatan = request.args.get('penempatan', 'N/A')
    status_laptop = request.args.get('status_laptop', 'N/A')
    kondisi = request.args.get('kondisi', 'N/A')
    kelengkapan = request.args.get('kelengkapan', 'N/A')
    tahun_beli = request.args.get('tahun_beli', 'N/A')
    kerusakan = request.args.get('kerusakan', 'Tidak ada')
    
    def sanitize(val):
        val_str = str(val)
        if val_str.startswith(('=', '+', '-', '@')):
            return "'" + val_str
        return val_str

    si = io.StringIO()
    cw = csv.writer(si)
    
    cw.writerow(['[DATA PENGGUNA & UNIT]'])
    cw.writerow(['Nama Lengkap', sanitize(nama)])
    cw.writerow(['Jabatan', sanitize(jabatan)])
    cw.writerow(['Perusahaan', sanitize(perusahaan)])
    cw.writerow(['Penempatan', sanitize(penempatan)])
    cw.writerow(['Status Laptop', sanitize(status_laptop)])
    cw.writerow(['Kondisi Fisik', sanitize(kondisi)])
    cw.writerow(['Kelengkapan', sanitize(kelengkapan)])
    cw.writerow(['Tahun Pembelian', sanitize(tahun_beli)])
    cw.writerow(['Kerusakan / Keluhan', sanitize(kerusakan)])
    cw.writerow([]) 
    
    cw.writerow(['Kategori', 'Komponen/Parameter', 'Detail'])
    cw.writerow(['Perangkat', 'Merk/Model', sanitize(hw_data['perangkat']['merk'])])
    cw.writerow(['Perangkat', 'OS Platform', sanitize(hw_data['perangkat']['os'])])
    cw.writerow(['Perangkat', 'Arsitektur', sanitize(hw_data['perangkat']['arsitektur'])])
    cw.writerow(['CPU', 'Model', sanitize(hw_data['cpu']['model'])])
    cw.writerow(['CPU', 'Core Fisik', sanitize(hw_data['cpu']['cores_fisik'])])
    cw.writerow(['CPU', 'Total Thread', sanitize(hw_data['cpu']['total_thread'])])
    cw.writerow(['CPU', 'Kecepatan', sanitize(hw_data['cpu']['kecepatan'])])
    cw.writerow(['RAM', 'Total RAM', sanitize(hw_data['ram']['total'])])
    cw.writerow(['RAM', 'Terpakai', f"{hw_data['ram']['used']} ({hw_data['ram']['percent']}%)"])
    
    cw.writerow(['Baterai', 'Persentase', sanitize(hw_data['battery']['percent'])])
    cw.writerow(['Baterai', 'Kesehatan', sanitize(hw_data['battery']['health'])])
    cw.writerow(['Baterai', 'Status', sanitize(hw_data['battery']['status'])])
    cw.writerow(['Baterai', 'Waktu Tersisa', sanitize(hw_data['battery']['time_left'])])
    
    for idx, disk_f in enumerate(hw_data['disk']['fisik'], 1):
        cw.writerow(['Disk Fisik', f'Media {idx}', sanitize(disk_f)])
    for part in hw_data['disk']['logis']:
        cw.writerow(['Partisi Logis', f"Drive {part['drive']}", f"Total: {part['total']} | Sisa: {part['free']} ({part['percent']} Terpakai)"])
    for idx, gpu in enumerate(hw_data['gpu'], 1):
        cw.writerow(['GPU', f'Unit {idx}', sanitize(gpu)])

    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = "attachment; filename=laporan_inspeksi_hardware.csv"
    output.headers["Content-type"] = "text/csv; charset=utf-8"
    return output

@app.route('/export/pdf')
def export_pdf():
    hw_data = detector.get_all_info()
    
    nama = request.args.get('nama', 'N/A')
    jabatan = request.args.get('jabatan', 'N/A')
    perusahaan = request.args.get('perusahaan', 'N/A')
    penempatan = request.args.get('penempatan', 'N/A')
    status_laptop = request.args.get('status_laptop', 'N/A')
    kondisi = request.args.get('kondisi', 'N/A')
    kelengkapan = request.args.get('kelengkapan', 'N/A')
    tahun_beli = request.args.get('tahun_beli', 'N/A')
    kerusakan = request.args.get('kerusakan', 'Tidak ada')
    
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    
    pdf.set_font("Arial", style='B', size=16)
    pdf.cell(200, 10, txt="LAPORAN INSPEKSI & DIAGNOSTIK LAPTOP", ln=True, align='C')
    pdf.ln(5)
    
    pdf.set_font("Arial", style='B', size=12)
    pdf.cell(200, 8, txt="[DATA PENGGUNA & STATUS UNIT]", ln=True)
    pdf.set_font("Arial", size=10)
    pdf.cell(200, 5, txt=f" Nama Lengkap    : {nama}", ln=True)
    pdf.cell(200, 5, txt=f" Jabatan         : {jabatan}", ln=True)
    pdf.cell(200, 5, txt=f" Perusahaan      : {perusahaan} (Penempatan: {penempatan})", ln=True)
    pdf.cell(200, 5, txt=f" Status Laptop   : {status_laptop}", ln=True)
    pdf.cell(200, 5, txt=f" Kondisi Fisik   : {kondisi}", ln=True)
    pdf.cell(200, 5, txt=f" Kelengkapan     : {kelengkapan}", ln=True)
    pdf.cell(200, 5, txt=f" Tahun Pembelian : {tahun_beli}", ln=True)
    pdf.cell(200, 5, txt=f" Keluhan/Kerusakan: {kerusakan}", ln=True)
    pdf.ln(5)
    
    pdf.set_font("Arial", style='B', size=12)
    pdf.cell(200, 8, txt="[PERANGKAT & SISTEM OPERASI]", ln=True)
    pdf.set_font("Arial", size=10)
    pdf.cell(200, 5, txt=f" Merk / Model    : {hw_data['perangkat']['merk']}", ln=True)
    pdf.cell(200, 5, txt=f" OS Platform     : {hw_data['perangkat']['os']}", ln=True)
    pdf.cell(200, 5, txt=f" Arsitektur      : {hw_data['perangkat']['arsitektur']}", ln=True)
    pdf.ln(4)
    
    pdf.set_font("Arial", style='B', size=12)
    pdf.cell(200, 8, txt="[PROSESOR / CPU]", ln=True)
    pdf.set_font("Arial", size=10)
    pdf.cell(200, 5, txt=f" Model CPU       : {hw_data['cpu']['model']}", ln=True)
    pdf.cell(200, 5, txt=f" Core & Thread   : {hw_data['cpu']['cores_fisik']} Cores / {hw_data['cpu']['total_thread']} Threads", ln=True)
    pdf.cell(200, 5, txt=f" Kecepatan       : {hw_data['cpu']['kecepatan']}", ln=True)
    pdf.ln(4)

    pdf.set_font("Arial", style='B', size=12)
    pdf.cell(200, 8, txt="[MEMORI / RAM]", ln=True)
    pdf.set_font("Arial", size=10)
    pdf.cell(200, 5, txt=f" Total RAM       : {hw_data['ram']['total']}", ln=True)
    pdf.cell(200, 5, txt=f" RAM Terpakai    : {hw_data['ram']['used']} ({hw_data['ram']['percent']}%)", ln=True)
    pdf.ln(4)

    pdf.set_font("Arial", style='B', size=12)
    pdf.cell(200, 8, txt="[PENYIMPANAN / DISK]", ln=True)
    pdf.set_font("Arial", style='I', size=10)
    pdf.cell(200, 5, txt=" Media Fisik:", ln=True)
    pdf.set_font("Arial", size=10)
    for disk_f in hw_data['disk']['fisik']:
        pdf.cell(200, 5, txt=f"   - {disk_f}", ln=True)
    pdf.set_font("Arial", style='I', size=10)
    pdf.cell(200, 5, txt=" Struktur Logis:", ln=True)
    pdf.set_font("Arial", size=10)
    for part in hw_data['disk']['logis']:
        pdf.cell(200, 5, txt=f"   - Drive {part['drive']} ({part['fstype']}) -> Total: {part['total']} | Sisa: {part['free']}", ln=True)
    pdf.ln(4)

    pdf.set_font("Arial", style='B', size=12)
    pdf.cell(200, 8, txt="[KARTU GRAFIS / GPU]", ln=True)
    pdf.set_font("Arial", size=10)
    for idx, gpu in enumerate(hw_data['gpu'], 1):
        pdf.cell(200, 5, txt=f" GPU {idx}           : {gpu}", ln=True)
    pdf.ln(4)

    pdf.set_font("Arial", style='B', size=12)
    pdf.cell(200, 8, txt="[KESEHATAN BATERAI]", ln=True)
    pdf.set_font("Arial", size=10)
    pdf.cell(200, 5, txt=f" Persentase      : {hw_data['battery']['percent']}", ln=True)
    pdf.cell(200, 5, txt=f" Kesehatan       : {hw_data['battery']['health']}", ln=True)
    pdf.cell(200, 5, txt=f" Status          : {hw_data['battery']['status']}", ln=True)
    pdf.cell(200, 5, txt=f" Waktu Tersisa   : {hw_data['battery']['time_left']}", ln=True)

    response = make_response(pdf.output(dest='S').encode('latin-1', errors='replace'))
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = 'attachment; filename=laporan_inspeksi_hardware.pdf'
    return response

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=8080, debug=False)