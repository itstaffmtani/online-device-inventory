<# :
@echo off
title Cek Laptop - MTani Inventory
powershell -NoProfile -ExecutionPolicy Bypass -Command "$src=[IO.File]::ReadAllText('%~f0'); Invoke-Expression $src"
exit /b
: #>
# ============================================================================
#  Check-Laptop.bat â€” Collector spek laptop untuk Windows (online-device-inventory)
# ----------------------------------------------------------------------------
#  Cara kerja:
#    1. Deteksi spek laptop (hostname, serial, CPU, RAM, disk, baterai, dll)
#    2. Ambil SNAPSHOT beban RAM saat ini
#    3. Buka browser ke form server, spek dibawa lewat URL query param
#
#  Tanpa install apa pun â€” hanya pakai PowerShell + WMI/CIM bawaan Windows.
#  Catatan: data kapasitas baterai (Wh) butuh namespace root\wmi; pada beberapa
#  PC desktop / tanpa baterai data ini kosong (otomatis dilewati).
# ============================================================================

# --- Konfigurasi: alamat server form ---------------------------------------
# Bisa di-override lewat environment variable SERVER_BASE_URL, atau edit di sini.
$ServerBaseUrl = $env:SERVER_BASE_URL
if ([string]::IsNullOrWhiteSpace($ServerBaseUrl)) {
    $ServerBaseUrl = "http://127.0.0.1:8080"
}
$ServerBaseUrl = $ServerBaseUrl.TrimEnd('/')

# Kumpulan parameter yang akan dikirim ke form (param => nilai)
$params = [ordered]@{}

function Set-Param {
    param([string]$Nama, $Nilai)
    # Hanya isi bila nilai terdeteksi & bukan placeholder kosong/OEM
    if ($null -eq $Nilai) { return }
    $teks = "$Nilai".Trim()
    if ([string]::IsNullOrWhiteSpace($teks)) { return }
    $kosong = @("to be filled by o.e.m.", "default string", "n/a", "none", "0", "unknown", "system serial number")
    if ($kosong -contains $teks.ToLower()) { return }
    $params[$Nama] = $teks
}

Write-Host "Mendeteksi spesifikasi laptop, mohon tunggu..." -ForegroundColor Cyan

# --- Hostname ---------------------------------------------------------------
try {
    Set-Param "hostname" $env:COMPUTERNAME
} catch {}

# --- MAC address (adapter aktif pertama) ------------------------------------
try {
    $adapter = Get-CimInstance Win32_NetworkAdapter -ErrorAction Stop |
        Where-Object { $_.NetEnabled -eq $true -and $_.MACAddress -and $_.PhysicalAdapter -eq $true } |
        Select-Object -First 1
    if (-not $adapter) {
        $adapter = Get-CimInstance Win32_NetworkAdapterConfiguration -ErrorAction Stop |
            Where-Object { $_.MACAddress } | Select-Object -First 1
    }
    if ($adapter -and $adapter.MACAddress) {
        Set-Param "mac" ($adapter.MACAddress.ToUpper())
    }
} catch {}

# --- Serial, brand, model (BIOS / ComputerSystem) ---------------------------
try {
    $bios = Get-CimInstance Win32_BIOS -ErrorAction Stop
    Set-Param "serial" $bios.SerialNumber
} catch {}

try {
    $cs = Get-CimInstance Win32_ComputerSystem -ErrorAction Stop
    Set-Param "brand" $cs.Manufacturer
    Set-Param "model" $cs.Model
} catch {}

# --- CPU --------------------------------------------------------------------
try {
    $cpu = Get-CimInstance Win32_Processor -ErrorAction Stop | Select-Object -First 1
    Set-Param "cpu"           $cpu.Name
    Set-Param "cpu_cores"     $cpu.NumberOfCores
    Set-Param "cpu_threads"   $cpu.NumberOfLogicalProcessors
    Set-Param "cpu_speed_mhz" $cpu.MaxClockSpeed
} catch {}

# Arsitektur CPU/OS (x64 / x86 / arm64)
try {
    $arch = $env:PROCESSOR_ARCHITECTURE
    switch -Regex ($arch) {
        "AMD64" { Set-Param "cpu_arch" "x64" }
        "x86"   { Set-Param "cpu_arch" "x86" }
        "ARM64" { Set-Param "cpu_arch" "arm64" }
        default { Set-Param "cpu_arch" $arch }
    }
} catch {}

# --- GPU (abaikan virtual / basic display) ----------------------------------
try {
    $gpus = Get-CimInstance Win32_VideoController -ErrorAction Stop |
        Where-Object {
            $_.Name -and
            $_.Name -notmatch "Virtual|Hyper-V|Basic|Remote|Mirror"
        } | Select-Object -ExpandProperty Name
    if ($gpus) {
        Set-Param "gpu" (($gpus | Select-Object -Unique) -join ", ")
    }
} catch {}

# --- RAM total, tipe, kecepatan ---------------------------------------------
try {
    $mem = Get-CimInstance Win32_PhysicalMemory -ErrorAction Stop
    if ($mem) {
        $totalBytes = ($mem | Measure-Object -Property Capacity -Sum).Sum
        if ($totalBytes -gt 0) {
            Set-Param "ram_gb" ([math]::Round($totalBytes / 1GB))
        }

        # Kecepatan (ambil yang paling umum / pertama yang valid)
        $speed = ($mem | Where-Object { $_.Speed } | Select-Object -First 1).Speed
        if ($speed) { Set-Param "ram_speed_mhz" $speed }

        # Tipe RAM (SMBIOSMemoryType lebih akurat dari MemoryType)
        $tipeKode = ($mem | Select-Object -First 1).SMBIOSMemoryType
        $tipeMap = @{
            20 = "DDR"; 21 = "DDR2"; 24 = "DDR3"; 26 = "DDR4"; 34 = "DDR5";
            35 = "DDR5"; 30 = "LPDDR3"; 31 = "LPDDR4"; 32 = "LPDDR4"; 33 = "LPDDR5"
        }
        if ($tipeKode -and $tipeMap.ContainsKey([int]$tipeKode)) {
            Set-Param "ram_type" $tipeMap[[int]$tipeKode]
        }
    }
} catch {}

# Fallback total RAM bila Win32_PhysicalMemory tidak terbaca
if (-not $params.Contains("ram_gb")) {
    try {
        $cs2 = Get-CimInstance Win32_ComputerSystem -ErrorAction Stop
        if ($cs2.TotalPhysicalMemory -gt 0) {
            Set-Param "ram_gb" ([math]::Round($cs2.TotalPhysicalMemory / 1GB))
        }
    } catch {}
}

# --- SNAPSHOT beban RAM saat ini --------------------------------------------
try {
    $os = Get-CimInstance Win32_OperatingSystem -ErrorAction Stop
    $totalKb = [double]$os.TotalVisibleMemorySize
    $freeKb  = [double]$os.FreePhysicalMemory
    if ($totalKb -gt 0) {
        $usedKb  = $totalKb - $freeKb
        $usedGb  = [math]::Round($usedKb / 1MB, 1)          # KB -> GB
        $usedPct = [math]::Round(($usedKb / $totalKb) * 100)
        Set-Param "ram_usage_gb"  $usedGb
        # ram_usage_pct boleh 0? praktis tak akan 0; kirim apa adanya
        $params["ram_usage_pct"] = $usedPct
    }
} catch {}

# --- Disk fisik: pisahkan SSD vs HDD, deteksi NVMe/SATA ---------------------
try {
    $disks = Get-PhysicalDisk -ErrorAction Stop
    $ssdBytes = 0; $hddBytes = 0; $ssdBus = ""
    foreach ($d in $disks) {
        switch ("$($d.MediaType)".ToUpper()) {
            "SSD" {
                $ssdBytes += $d.Size
                if ("$($d.BusType)".ToUpper() -eq "NVME") { $ssdBus = "NVMe" }
                elseif (-not $ssdBus) { $ssdBus = "SATA" }
            }
            "HDD" { $hddBytes += $d.Size }
            default {
                # MediaType "Unspecified": tebak via BusType
                if ("$($d.BusType)".ToUpper() -eq "NVME") {
                    $ssdBytes += $d.Size; $ssdBus = "NVMe"
                } else {
                    $hddBytes += $d.Size
                }
            }
        }
    }
    if ($ssdBytes -gt 0) {
        Set-Param "ssd_gb" ([math]::Round($ssdBytes / 1GB))
        if ($ssdBus) { Set-Param "ssd_type" $ssdBus }
    }
    if ($hddBytes -gt 0) {
        Set-Param "hdd_gb" ([math]::Round($hddBytes / 1GB))
    }
} catch {}

# --- OS + kapasitas partisi sistem ------------------------------------------
try {
    $osinfo = Get-CimInstance Win32_OperatingSystem -ErrorAction Stop
    # Bersihkan nama: "Microsoft Windows 11 Home" -> "Windows 11 Home"
    $namaOs = ($osinfo.Caption -replace "^Microsoft\s+", "").Trim()
    Set-Param "os" $namaOs
} catch {}

try {
    $sysDrive = $env:SystemDrive  # mis. "C:"
    $vol = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='$sysDrive'" -ErrorAction Stop
    if ($vol -and $vol.Size -gt 0) {
        Set-Param "os_total_gb" ([math]::Round($vol.Size / 1GB))
        Set-Param "os_free_gb"  ([math]::Round($vol.FreeSpace / 1GB))
    }
} catch {}

# --- Baterai: persen + kapasitas Wh -----------------------------------------
try {
    $batt = Get-CimInstance Win32_Battery -ErrorAction Stop | Select-Object -First 1
    if ($batt -and $null -ne $batt.EstimatedChargeRemaining) {
        Set-Param "battery_pct" $batt.EstimatedChargeRemaining
    }
} catch {}

# Kapasitas penuh & desain (mWh -> Wh, bagi 1000) dari namespace root\wmi
try {
    $full = Get-CimInstance -Namespace "root\wmi" -ClassName BatteryFullChargedCapacity -ErrorAction Stop |
        Select-Object -First 1
    if ($full -and $full.FullChargedCapacity -gt 0) {
        Set-Param "battery_wh_full" ([math]::Round($full.FullChargedCapacity / 1000, 1))
    }
} catch {}

try {
    $design = Get-CimInstance -Namespace "root\wmi" -ClassName BatteryStaticData -ErrorAction Stop |
        Select-Object -First 1
    if ($design -and $design.DesignedCapacity -gt 0) {
        Set-Param "battery_wh_design" ([math]::Round($design.DesignedCapacity / 1000, 1))
    }
} catch {}

# --- Bangun URL & buka browser ----------------------------------------------
Add-Type -AssemblyName System.Web -ErrorAction SilentlyContinue

$pasangan = @()
foreach ($k in $params.Keys) {
    $nilai = "$($params[$k])"
    try {
        $enc = [System.Web.HttpUtility]::UrlEncode($nilai)
    } catch {
        $enc = [System.Uri]::EscapeDataString($nilai)
    }
    $pasangan += "$k=$enc"
}
$query = $pasangan -join "&"
$url = "$ServerBaseUrl/form?$query"

Write-Host ""
Write-Host "Spesifikasi terdeteksi ($($params.Count) data):" -ForegroundColor Green
foreach ($k in $params.Keys) {
    Write-Host ("  {0,-18}: {1}" -f $k, $params[$k])
}

Write-Host ""
Write-Host "URL form:" -ForegroundColor Cyan
Write-Host $url
Write-Host ""
Write-Host "Membuka form di browser..." -ForegroundColor Green

try {
    Start-Process $url
    Write-Host "Browser dibuka. Silakan lengkapi data diri Anda pada form, lalu klik Kirim." -ForegroundColor Yellow
} catch {
    Write-Host "Tidak bisa membuka browser otomatis. Salin & buka URL di atas secara manual." -ForegroundColor Red
}

Write-Host ""
Write-Host "Tekan Enter untuk menutup jendela ini..."
[void](Read-Host)
