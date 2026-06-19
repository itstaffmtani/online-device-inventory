from flask import Flask, render_template, make_response
from hardware_service import HardwareDetector
import csv
import io
from fpdf import FPDF

app = Flask(__name__)
detector = HardwareDetector()

@app.route('/')
def index():
    hw_data = detector.get_all_info()
    return render_template('index.html', data=hw_data)

@app.route('/export/csv')
def export_csv():
    hw_data = detector.get_all_info()
    
    # OWASP CSV Injection Mitigation
    def sanitize(val):
        val_str = str(val)
        if val_str.startswith(('=', '+', '-', '@')):
            return "'" + val_str
        return val_str

    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerow(['Kategori', 'Komponen/Parameter', 'Detail'])
    
    # Sistem & Perangkat
    cw.writerow(['Perangkat', 'Merk/Model', sanitize(hw_data['perangkat']['merk'])])
    cw.writerow(['Perangkat', 'OS Platform', sanitize(hw_data['perangkat']['os'])])
    cw.writerow(['Perangkat', 'Arsitektur', sanitize(hw_data['perangkat']['arsitektur'])])
    
    # CPU
    cw.writerow(['CPU', 'Model', sanitize(hw_data['cpu']['model'])])
    cw.writerow(['CPU', 'Core Fisik', sanitize(hw_data['cpu']['cores_fisik'])])
    cw.writerow(['CPU', 'Total Thread', sanitize(hw_data['cpu']['total_thread'])])
    cw.writerow(['CPU', 'Kecepatan', sanitize(hw_data['cpu']['kecepatan'])])
    
    # RAM
    cw.writerow(['RAM', 'Total RAM', sanitize(hw_data['ram']['total'])])
    cw.writerow(['RAM', 'Terpakai', f"{hw_data['ram']['used']} ({hw_data['ram']['percent']}%)"])
    
    # Disk Fisik
    for idx, disk_f in enumerate(hw_data['disk']['fisik'], 1):
        cw.writerow(['Disk Fisik', f'Media {idx}', sanitize(disk_f)])
        
    # Partisi Logis
    for part in hw_data['disk']['logis']:
        cw.writerow(['Partisi Logis', f"Drive {part['drive']}", f"Total: {part['total']} | Sisa: {part['free']} ({part['percent']} Terpakai)"])
        
    # GPU
    for idx, gpu in enumerate(hw_data['gpu'], 1):
        cw.writerow(['GPU', f'Unit {idx}', sanitize(gpu)])

    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = "attachment; filename=hardware_report_lengkap.csv"
    output.headers["Content-type"] = "text/csv; charset=utf-8"
    return output

@app.route('/export/pdf')
def export_pdf():
    hw_data = detector.get_all_info()
    
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    
    # Header
    pdf.set_font("Arial", style='B', size=16)
    pdf.cell(200, 10, txt="LAPORAN DIAGNOSTIK SPESIFIKASI SISTEM", ln=True, align='C')
    pdf.ln(10)
    
    pdf.set_font("Arial", size=12)
    # Section 1
    pdf.set_font("Arial", style='B', size=12)
    pdf.cell(200, 8, txt="[PERANGKAT & SISTEM OPERASI]", ln=True)
    pdf.set_font("Arial", size=11)
    pdf.cell(200, 6, txt=f" Merk / Model : {hw_data['perangkat']['merk']}", ln=True)
    pdf.cell(200, 6, txt=f" OS Platform  : {hw_data['perangkat']['os']}", ln=True)
    pdf.cell(200, 6, txt=f" Arsitektur   : {hw_data['perangkat']['arsitektur']}", ln=True)
    pdf.ln(4)
    
    # Section 2
    pdf.set_font("Arial", style='B', size=12)
    pdf.cell(200, 8, txt="[PROSESOR / CPU]", ln=True)
    pdf.set_font("Arial", size=11)
    pdf.cell(200, 6, txt=f" Model CPU    : {hw_data['cpu']['model']}", ln=True)
    pdf.cell(200, 6, txt=f" Core Fisik   : {hw_data['cpu']['cores_fisik']} Cores", ln=True)
    pdf.cell(200, 6, txt=f" Total Thread : {hw_data['cpu']['total_thread']} Threads", ln=True)
    pdf.cell(200, 6, txt=f" Kecepatan    : {hw_data['cpu']['kecepatan']}", ln=True)
    pdf.ln(4)

    # Section 3
    pdf.set_font("Arial", style='B', size=12)
    pdf.cell(200, 8, txt="[MEMORI / RAM]", ln=True)
    pdf.set_font("Arial", size=11)
    pdf.cell(200, 6, txt=f" Total RAM    : {hw_data['ram']['total']}", ln=True)
    pdf.cell(200, 6, txt=f" RAM Terpakai : {hw_data['ram']['used']} ({hw_data['ram']['percent']}%)", ln=True)
    pdf.ln(4)

    # Section 4
    pdf.set_font("Arial", style='B', size=12)
    pdf.cell(200, 8, txt="[PENYIMPANAN / DISK]", ln=True)
    pdf.set_font("Arial", style='I', size=11)
    pdf.cell(200, 6, txt=" Tipe Media Penyimpanan (Fisik):", ln=True)
    pdf.set_font("Arial", size=11)
    for disk_f in hw_data['disk']['fisik']:
        pdf.cell(200, 6, txt=f"   - {disk_f}", ln=True)
        
    pdf.set_font("Arial", style='I', size=11)
    pdf.cell(200, 6, txt=" Status Partisi (Logis):", ln=True)
    pdf.set_font("Arial", size=11)
    for part in hw_data['disk']['logis']:
        pdf.cell(200, 6, txt=f"   - Drive {part['drive']} ({part['fstype']}) -> Total: {part['total']} | Sisa: {part['free']}", ln=True)
    pdf.ln(4)

    # Section 5
    pdf.set_font("Arial", style='B', size=12)
    pdf.cell(200, 8, txt="[KARTU GRAFIS / GPU]", ln=True)
    pdf.set_font("Arial", size=11)
    for idx, gpu in enumerate(hw_data['gpu'], 1):
        pdf.cell(200, 6, txt=f" GPU {idx}        : {gpu}", ln=True)

    response = make_response(pdf.output(dest='S').encode('latin-1', errors='replace'))
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = 'attachment; filename=hardware_report_lengkap.pdf'
    return response

if __name__ == '__main__':
    # Pastikan port diganti jika port 5000 kamu masih bentrok
    app.run(host='127.0.0.1', port=8080, debug=False)