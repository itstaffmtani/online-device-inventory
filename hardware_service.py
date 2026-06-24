import platform
import psutil
import cpuinfo
import subprocess
import json
import uuid
import socket

class HardwareDetector:
    @staticmethod
    def konversi_ukuran(bytes, suffix="B"):
        factor = 1024
        for unit in ["", "K", "M", "G", "T", "P"]:
            if bytes < factor:
                return f"{bytes:.2f} {unit}{suffix}"
            bytes /= factor
            
    def _dapatkan_hostname(self):
        try:
            return socket.gethostname()
        except:
            return "Tidak diketahui"
            
    def _dapatkan_mac_address(self):
        try:
            mac = uuid.getnode()
            return ':'.join(['{:02x}'.format((mac >> elements) & 0xff) for elements in range(0,2*6,2)][::-1]).upper()
        except:
            return "Tidak terdeteksi"

    def _dapatkan_serial_number(self):
        sistem_os = platform.system()
        try:
            if sistem_os == "Windows":
                cmd = "wmic bios get serialnumber"
                output = subprocess.check_output(cmd, shell=True).decode()
                baris = [l.strip() for l in output.split('\n') if l.strip()]
                sn = baris[-1] if len(baris) > 1 else ""
                return sn if sn.lower() not in ["to be filled by o.e.m.", "default string", "0", "n/a", "none"] else "Kosong/OEM"
            elif sistem_os == "Linux":
                return subprocess.check_output("cat /sys/class/dmi/id/product_serial", shell=True).decode().strip()
            elif sistem_os == "Darwin":
                output = subprocess.check_output("system_profiler SPHardwareDataType | grep 'Serial Number'", shell=True).decode().strip()
                return output.split(":")[-1].strip()
        except Exception:
            pass
        return "Tidak dapat membaca S/N"

    def dapatkan_merk_laptop(self):
        sistem_os = platform.system()
        try:
            if sistem_os == "Windows":
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
                cmd = 'powershell "Get-PhysicalDisk | Select-Object Model, MediaType, BusType | ConvertTo-Json"'
                output = subprocess.check_output(cmd, shell=True).decode()
                try:
                    disks = json.loads(output)
                    if isinstance(disks, dict): disks = [disks]
                    for d in disks:
                        model = d.get('Model', 'Unknown').strip()
                        tipe = d.get('MediaType', 'Unknown')
                        bus = d.get('BusType', '')
                        
                        if tipe.upper() == "SSD" and bus.upper() == "NVME":
                            tipe = "SSD (NVMe)"
                        elif tipe.upper() == "SSD":
                            tipe = "SSD (SATA/M.2)"
                            
                        info_disk.append(f"{model} [{tipe}]")
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
                        tipe = "HDD" if rota == "1" else "SSD"
                        if "nvme" in nama_device.lower():
                            tipe = "SSD (NVMe)"
                        info_disk.append(f"/dev/{nama_device} - {model} [{tipe}]")
        except Exception:
            pass
        return info_disk if info_disk else ["Informasi fisik disk tidak tersedia"]

    def dapatkan_info_gpu(self):
        sistem_os = platform.system()
        gpus = []
        try:
            if sistem_os == "Windows":
                gpu_info = subprocess.check_output("wmic path win32_VideoController get name", shell=True).decode()
                lines = [line.strip() for line in gpu_info.split('\n') if line.strip() and "Name" not in line]
                for gpu in lines:
                    if "Virtual" not in gpu and "Hyper-V" not in gpu and "Basic" not in gpu:
                        gpus.append(gpu)
            elif sistem_os == "Linux":
                gpu_info = subprocess.check_output("lspci | grep -i vga", shell=True).decode()
                for line in gpu_info.strip().split('\n'):
                    if line: gpus.append(line.split(': ')[-1])
            elif sistem_os == "Darwin":
                gpu_info = subprocess.check_output("system_profiler SPDisplaysDataType | grep Chipset", shell=True).decode()
                gpus = [line.strip().replace("Chipset Model: ", "") for line in gpu_info.split('\n') if line.strip()]
        except Exception as e:
            gpus.append(f"Gagal membaca informasi GPU")
        
        return gpus if gpus else ["Tidak ada GPU yang terdeteksi"]

    @staticmethod
    def _format_waktu_baterai(secs):
        """Mengubah detik sisa baterai menjadi string jam:menit yang mudah dibaca."""
        if secs is None or secs < 0:
            return "-"
        jam, sisa = divmod(int(secs), 3600)
        menit = sisa // 60
        return f"{jam} jam {menit} menit"

    def _dapatkan_info_baterai(self):
        """Mendeteksi persentase, status, perkiraan waktu, dan kesehatan baterai."""
        pct = "-"
        status = "-"
        time_left = "-"
        health = "-"
        wh_current = "-"
        wh_design = "-"

        # 1. Dapatkan info dasar lintas platform (persentase, status, waktu tersisa)
        try:
            battery = psutil.sensors_battery()
            if battery:
                pct = f"{battery.percent}%"
                if battery.power_plugged:
                    status = "Penuh" if battery.percent >= 100 else "Mengisi Daya (Charging)"
                else:
                    status = "Memakai Baterai (Discharging)"
                    time_left = self._format_waktu_baterai(battery.secsleft)
            else:
                status = "Tidak ada baterai (PC Desktop)"
        except Exception:
            pass

        # 2. Dapatkan statistik mWh/Wh spesifik di Windows (Sama dengan script batch)
        if platform.system() == "Windows":
            try:
                # Opsional alternatif mWh jika root/wmi dibatasi: gunakan wmic / powershell batteryreport
                output = subprocess.check_output('powershell "Get-WmiObject -Namespace root\\wmi -Class BatteryStaticData | Select-Object DesignedCapacity | ConvertTo-Json"', shell=True).decode()
                data_static = json.loads(output) if output.strip() else {}

                output_curr = subprocess.check_output('powershell "Get-WmiObject -Namespace root\\wmi -Class BatteryFullChargedCapacity | Select-Object FullChargedCapacity | ConvertTo-Json"', shell=True).decode()
                data_curr = json.loads(output_curr) if output_curr.strip() else {}

                # Ambil nilai mWh dan konversi ke Wh (dibagi 1000)
                designed = data_static.get('DesignedCapacity') if isinstance(data_static, dict) else None
                full = data_curr.get('FullChargedCapacity') if isinstance(data_curr, dict) else None

                if designed:
                    wh_design = f"{round(designed / 1000, 2)} Wh"
                if full:
                    wh_current = f"{round(full / 1000, 2)} Wh"

                # Kesehatan = kapasitas penuh saat ini / kapasitas desain
                if designed and full:
                    health = f"{round(full / designed * 100, 1)}% ({wh_current} / {wh_design})"
            except Exception:
                # Fallback jika WMI kelas root/wmi kosong/tidak diizinkan (pada beberapa device PC Desktop)
                if pct != "-":
                    wh_current = "N/A (PC Desktop/No Battery Data)"
                    wh_design = "N/A"
                    health = "N/A"

        return {
            "percent": pct,
            "status": status,
            "time_left": time_left,
            "health": health,
            "wh_current": wh_current,
            "wh_design": wh_design,
        }

    def get_all_info(self):
        cpu_info = cpuinfo.get_cpu_info()
        svmem = psutil.virtual_memory()
        
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

        cpu_speed = "Tidak diketahui"
        try:
            freq = psutil.cpu_freq()
            if freq: cpu_speed = f"{freq.max:.2f} MHz"
        except Exception:
            pass

        os_name = f"{platform.system()} {platform.release()} ({platform.version()})"
        os_arch = platform.machine()
        full_os_str = f"{os_name} {os_arch}".strip()

        return {
            "perangkat": {
                "hostname": self._dapatkan_hostname(),
                "mac_address": self._dapatkan_mac_address(),
                "serial_number": self._dapatkan_serial_number(),
                "merk": self.dapatkan_merk_laptop(),
                "os": full_os_str,
                "arsitektur": os_arch
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
            "gpu": self.dapatkan_info_gpu(),
            "battery": self._dapatkan_info_baterai() # Tambahan objek data baterai
        }