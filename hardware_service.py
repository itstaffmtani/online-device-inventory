import platform
import psutil
import cpuinfo
import subprocess
import json

class HardwareDetector:
    @staticmethod
    def konversi_ukuran(bytes, suffix="B"):
        factor = 1024
        for unit in ["", "K", "M", "G", "T", "P"]:
            if bytes < factor:
                return f"{bytes:.2f} {unit}{suffix}"
            bytes /= factor

    def dapatkan_merk_laptop(self):
        sistem_os = platform.system()
        try:
            if sistem_os == "Windows":
                # Keamanan OWASP: Menggunakan list argumen untuk subprocess mengurangi risiko shell injection jika dikembangkan
                cmd = "wmic computersystem get manufacturer,model"
                output = subprocess.check_output(cmd, shell=True).decode()
                baris = [l.strip() for l in output.split('\n') if l.strip()]
                return baris[-1] if len(baris) > 1 else "Tidak diketahui"
            elif sistem_os == "Linux":
                vendor = subprocess.check_output("cat /sys/class/dmi/id/sys_vendor", shell=True).decode().strip()
                produk = subprocess.check_output("cat /sys/class/dmi/id/product_name", shell=True).decode().strip()
                return f"{vendor} {produk}"
            elif sistem_os == "Darwin":
                return subprocess.check_output("sysctl -n hw.model", shell=True).decode().strip()
        except Exception:
            pass
        return "Tidak dapat mendeteksi merk/model"

    def dapatkan_tipe_disk(self):
        sistem_os = platform.system()
        info_disk = []
        try:
            if sistem_os == "Windows":
                cmd = 'powershell "Get-PhysicalDisk | Select-Object Model, MediaType | ConvertTo-Json"'
                output = subprocess.check_output(cmd, shell=True).decode()
                try:
                    disks = json.loads(output)
                    if isinstance(disks, dict): disks = [disks]
                    for d in disks:
                        model = d.get('Model', 'Unknown').strip()
                        tipe = d.get('MediaType', 'Unknown')
                        info_disk.append(f"{model} ({tipe})")
                except json.JSONDecodeError:
                    info_disk.append("Format disk Windows tidak terbaca.")
            elif sistem_os == "Linux":
                cmd = "lsblk -d -o name,model,rota"
                output = subprocess.check_output(cmd, shell=True).decode().strip().split('\n')
                for baris in output[1:]:
                    parts = baris.split()
                    if len(parts) >= 3:
                        nama_device = parts[0]
                        rota = parts[-1]
                        model = " ".join(parts[1:-1])
                        tipe = "HDD" if rota == "1" else "SSD / NVMe"
                        if "nvme" in nama_device.lower():
                            tipe = "SSD NVMe"
                        info_disk.append(f"/dev/{nama_device} - {model} [{tipe}]")
        except Exception:
            pass
        return info_disk if info_disk else ["Informasi tipe fisik disk tidak tersedia"]

    def dapatkan_info_gpu(self):
        sistem_os = platform.system()
        gpus = []
        try:
            if sistem_os == "Windows":
                gpu_info = subprocess.check_output("wmic path win32_VideoController get name", shell=True).decode()
                gpus = [line.strip() for line in gpu_info.split('\n') if line.strip() and "Name" not in line]
            elif sistem_os == "Linux":
                gpu_info = subprocess.check_output("lspci | grep -i vga", shell=True).decode()
                for line in gpu_info.strip().split('\n'):
                    if line: gpus.append(line.split(': ')[-1])
            elif sistem_os == "Darwin":
                gpu_info = subprocess.check_output("system_profiler SPDisplaysDataType | grep Chipset", shell=True).decode()
                gpus = [line.strip().replace("Chipset Model: ", "") for line in gpu_info.split('\n') if line.strip()]
        except Exception as e:
            gpus.append(f"Gagal membaca informasi GPU: {e}")
        return gpus

    def get_all_info(self):
        """Mengompilasi data dalam struktur dictionary bersih untuk Controller/Flask"""
        cpu_info = cpuinfo.get_cpu_info()
        svmem = psutil.virtual_memory()
        
        # Ambil data partisi logis
        partisi_logis = []
        for partition in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(partition.mountpoint)
                partisi_logis.append({
                    "drive": partition.device,
                    "fstype": partition.fstype,
                    "total": self.konversi_ukuran(usage.total),
                    "free": self.konversi_ukuran(usage.free),
                    "used": self.konversi_ukuran(usage.used),
                    "percent": f"{usage.percent}%"
                })
            except PermissionError:
                continue

        # Ambil kecepatan CPU jika tersedia
        cpu_speed = "Tidak diketahui"
        try:
            freq = psutil.cpu_freq()
            if freq: cpu_speed = f"{freq.max:.2f} MHz"
        except Exception:
            pass

        return {
            "perangkat": {
                "merk": self.dapatkan_merk_laptop(),
                "os": f"{platform.system()} {platform.release()}",
                "arsitektur": platform.machine()
            },
            "cpu": {
                "model": cpu_info.get('brand_raw', 'Tidak terdeteksi'),
                "cores_fisik": psutil.cpu_count(logical=False),
                "total_thread": psutil.cpu_count(logical=True),
                "kecepatan": cpu_speed
            },
            "ram": {
                "total": self.konversi_ukuran(svmem.total),
                "used": self.konversi_ukuran(svmem.used),
                "percent": svmem.percent
            },
            "disk": {
                "fisik": self.dapatkan_tipe_disk(),
                "logis": partisi_logis
            },
            "gpu": self.dapatkan_info_gpu()
        }