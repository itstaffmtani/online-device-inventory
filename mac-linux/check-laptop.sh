#!/usr/bin/env bash
# ============================================================================
#  check-laptop.sh — Collector spek laptop untuk macOS & Linux
#                  (online-device-inventory)
# ----------------------------------------------------------------------------
#  Cara kerja:
#    1. Deteksi spek laptop (hostname, serial, CPU, RAM, disk, baterai, dll)
#    2. Ambil SNAPSHOT beban RAM saat ini
#    3. Buka browser ke form server, spek dibawa lewat URL query param
#
#  Tanpa install apa pun — hanya pakai tool bawaan:
#    Linux : /proc, lscpu, free, lsblk, /sys/class/dmi, /sys/class/power_supply
#    macOS : sysctl, system_profiler, vm_stat, pmset, ioreg
#
#  Catatan: beberapa data DMI (serial/merk) di Linux mungkin butuh akses root;
#  bila tak terbaca, field-nya otomatis dilewati (bisa diisi manual di form).
# ============================================================================

# --- Konfigurasi: alamat server form ---------------------------------------
# Bisa di-override lewat environment variable SERVER_BASE_URL, atau edit di sini.
SERVER_BASE_URL="${SERVER_BASE_URL:-http://127.0.0.1:8080}"
SERVER_BASE_URL="${SERVER_BASE_URL%/}"   # buang trailing slash

OS="$(uname -s)"   # "Linux" atau "Darwin"

# Kumpulan param: array nama & nilai sejajar
PARAM_KEYS=()
PARAM_VALS=()

# Daftar nilai placeholder yang dianggap "tidak terdeteksi"
is_placeholder() {
    local v
    v="$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]' | sed 's/^ *//; s/ *$//')"
    case "$v" in
        ""|"to be filled by o.e.m."|"default string"|"n/a"|"none"|"0"|"unknown"|\
        "system serial number"|"system manufacturer"|"system product name"|\
        "not specified"|"not available")
            return 0 ;;
        *) return 1 ;;
    esac
}

# set_param NAMA NILAI  — simpan bila valid (bukan kosong/placeholder)
set_param() {
    local nama="$1"; shift
    local nilai="$*"
    # trim whitespace di ujung
    nilai="$(printf '%s' "$nilai" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')"
    if is_placeholder "$nilai"; then return; fi
    PARAM_KEYS+=("$nama")
    PARAM_VALS+=("$nilai")
}

# has_param NAMA  — cek apakah param sudah diisi
has_param() {
    local target="$1" k
    for k in "${PARAM_KEYS[@]}"; do
        [ "$k" = "$target" ] && return 0
    done
    return 1
}

# URL-encode RFC 3986 (pakai printf, tanpa dependensi eksternal)
urlencode() {
    local s="$1" out="" c i
    for (( i=0; i<${#s}; i++ )); do
        c="${s:$i:1}"
        case "$c" in
            [a-zA-Z0-9.~_-]) out+="$c" ;;
            *) out+="$(printf '%%%02X' "'$c")" ;;
        esac
    done
    printf '%s' "$out"
}

echo "Mendeteksi spesifikasi laptop, mohon tunggu..."

# ============================================================================
#  HOSTNAME (lintas platform)
# ============================================================================
set_param "hostname" "$(hostname 2>/dev/null)"

# ============================================================================
#  DETEKSI PER PLATFORM
# ============================================================================
if [ "$OS" = "Linux" ]; then
    # ---------- MAC address (interface non-loopback pertama yang aktif) -----
    mac=""
    for ifpath in /sys/class/net/*; do
        ifname="$(basename "$ifpath")"
        [ "$ifname" = "lo" ] && continue
        if [ -r "$ifpath/address" ]; then
            a="$(cat "$ifpath/address" 2>/dev/null)"
            if [ -n "$a" ] && [ "$a" != "00:00:00:00:00:00" ]; then
                # utamakan interface yang 'up'
                state="$(cat "$ifpath/operstate" 2>/dev/null)"
                if [ "$state" = "up" ]; then mac="$a"; break; fi
                [ -z "$mac" ] && mac="$a"
            fi
        fi
    done
    [ -n "$mac" ] && set_param "mac" "$(printf '%s' "$mac" | tr '[:lower:]' '[:upper:]')"

    # ---------- Serial / brand / model (DMI) --------------------------------
    [ -r /sys/class/dmi/id/product_serial ] && \
        set_param "serial" "$(cat /sys/class/dmi/id/product_serial 2>/dev/null)"
    [ -r /sys/class/dmi/id/sys_vendor ] && \
        set_param "brand" "$(cat /sys/class/dmi/id/sys_vendor 2>/dev/null)"
    [ -r /sys/class/dmi/id/product_name ] && \
        set_param "model" "$(cat /sys/class/dmi/id/product_name 2>/dev/null)"

    # ---------- Motherboard (vendor + nama board) ---------------------------
    # best-effort: gabungkan board_vendor + board_name bila terbaca
    mb_vendor=""; mb_name=""
    [ -r /sys/devices/virtual/dmi/id/board_vendor ] && \
        mb_vendor="$(cat /sys/devices/virtual/dmi/id/board_vendor 2>/dev/null)"
    [ -r /sys/devices/virtual/dmi/id/board_name ] && \
        mb_name="$(cat /sys/devices/virtual/dmi/id/board_name 2>/dev/null)"
    mb="$(printf '%s %s' "$mb_vendor" "$mb_name" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')"
    [ -n "$mb" ] && set_param "motherboard" "$mb"

    # ---------- CPU ---------------------------------------------------------
    if command -v lscpu >/dev/null 2>&1; then
        lscpu_out="$(LC_ALL=C lscpu 2>/dev/null)"
        cpu_model="$(printf '%s\n' "$lscpu_out" | grep -i '^Model name:' | head -1 | sed 's/^[^:]*: *//')"
        sockets="$(printf '%s\n' "$lscpu_out" | grep -i '^Socket(s):' | head -1 | sed 's/^[^:]*: *//')"
        cps="$(printf '%s\n' "$lscpu_out" | grep -i '^Core(s) per socket:' | head -1 | sed 's/^[^:]*: *//')"
        threads="$(printf '%s\n' "$lscpu_out" | grep -iE '^CPU\(s\):' | head -1 | sed 's/^[^:]*: *//')"
        arch="$(printf '%s\n' "$lscpu_out" | grep -i '^Architecture:' | head -1 | sed 's/^[^:]*: *//')"
        mhzmax="$(printf '%s\n' "$lscpu_out" | grep -i '^CPU max MHz:' | head -1 | sed 's/^[^:]*: *//')"

        [ -n "$cpu_model" ] && set_param "cpu" "$cpu_model"
        if [ -n "$sockets" ] && [ -n "$cps" ]; then
            set_param "cpu_cores" "$(( sockets * cps ))"
        elif [ -n "$cps" ]; then
            set_param "cpu_cores" "$cps"
        fi
        [ -n "$threads" ] && set_param "cpu_threads" "$threads"
        # normalisasi arsitektur
        case "$arch" in
            x86_64) set_param "cpu_arch" "x64" ;;
            aarch64|arm64) set_param "cpu_arch" "arm64" ;;
            i?86) set_param "cpu_arch" "x86" ;;
            "") : ;;
            *) set_param "cpu_arch" "$arch" ;;
        esac
        if [ -n "$mhzmax" ]; then
            # bulatkan ke integer MHz
            set_param "cpu_speed_mhz" "$(printf '%.0f' "$mhzmax" 2>/dev/null)"
        fi
    fi
    # Fallback CPU model dari /proc/cpuinfo
    if ! has_param "cpu" && [ -r /proc/cpuinfo ]; then
        m="$(grep -m1 -i 'model name' /proc/cpuinfo | sed 's/^[^:]*: *//')"
        set_param "cpu" "$m"
    fi
    # Fallback thread count dari /proc/cpuinfo
    if ! has_param "cpu_threads" && [ -r /proc/cpuinfo ]; then
        t="$(grep -c -i '^processor' /proc/cpuinfo)"
        [ "$t" -gt 0 ] && set_param "cpu_threads" "$t"
    fi
    # Fallback arsitektur
    if ! has_param "cpu_arch"; then
        case "$(uname -m)" in
            x86_64) set_param "cpu_arch" "x64" ;;
            aarch64|arm64) set_param "cpu_arch" "arm64" ;;
            i?86) set_param "cpu_arch" "x86" ;;
        esac
    fi

    # ---------- GPU ---------------------------------------------------------
    if command -v lspci >/dev/null 2>&1; then
        gpu="$(LC_ALL=C lspci 2>/dev/null | grep -iE 'vga|3d|display' | sed 's/^.*: //' | paste -sd ', ' -)"
        [ -n "$gpu" ] && set_param "gpu" "$gpu"
    fi

    # ---------- RAM total ---------------------------------------------------
    if [ -r /proc/meminfo ]; then
        mem_kb="$(grep -i '^MemTotal:' /proc/meminfo | awk '{print $2}')"
        if [ -n "$mem_kb" ] && [ "$mem_kb" -gt 0 ]; then
            # KB -> GB, bulatkan
            ram_gb="$(awk -v k="$mem_kb" 'BEGIN{printf "%.0f", k/1048576}')"
            set_param "ram_gb" "$ram_gb"
        fi
    fi

    # ---------- RAM tipe & kecepatan (dmidecode bila root) ------------------
    if command -v dmidecode >/dev/null 2>&1; then
        dmi_mem="$(dmidecode -t memory 2>/dev/null)"
        if [ -n "$dmi_mem" ]; then
            rtype="$(printf '%s\n' "$dmi_mem" | grep -i '^\s*Type:' | grep -ivE 'Unknown|None|Other' | head -1 | sed 's/^[^:]*: *//')"
            [ -n "$rtype" ] && set_param "ram_type" "$rtype"
            rspeed="$(printf '%s\n' "$dmi_mem" | grep -iE 'Configured Memory Speed|Configured Clock Speed|^\s*Speed:' | grep -oiE '[0-9]+ *MT/s|[0-9]+ *MHz' | grep -oE '[0-9]+' | head -1)"
            [ -n "$rspeed" ] && set_param "ram_speed_mhz" "$rspeed"

            # Slot RAM terisi: jumlah modul dgn Size berupa angka (bukan "No Module Installed")
            slots_used="$(printf '%s\n' "$dmi_mem" | grep -iE '^\s*Size:' | grep -ciE '[0-9]+ *[GM]B')"
            [ -n "$slots_used" ] && [ "$slots_used" -gt 0 ] && set_param "ram_slots_used" "$slots_used"
        fi

        # Total slot fisik + kapasitas maksimum board (dmidecode -t 16)
        dmi_arr="$(dmidecode -t 16 2>/dev/null)"
        if [ -n "$dmi_arr" ]; then
            slots_total="$(printf '%s\n' "$dmi_arr" | grep -iE 'Number Of Devices:' | head -1 | grep -oE '[0-9]+')"
            [ -n "$slots_total" ] && [ "$slots_total" -gt 0 ] && set_param "ram_slots_total" "$slots_total"
            # Maximum Capacity mis. "32 GB" / "64 GB" / "2 TB"
            maxcap="$(printf '%s\n' "$dmi_arr" | grep -iE 'Maximum Capacity:' | head -1 | sed 's/^[^:]*: *//')"
            maxnum="$(printf '%s' "$maxcap" | grep -oE '[0-9.]+' | head -1)"
            maxunit="$(printf '%s' "$maxcap" | grep -oiE '[TG]B' | head -1)"
            if [ -n "$maxnum" ]; then
                if printf '%s' "$maxunit" | grep -qi 'TB'; then
                    set_param "ram_max_gb" "$(awk -v n="$maxnum" 'BEGIN{printf "%.0f", n*1024}')"
                else
                    set_param "ram_max_gb" "$(awk -v n="$maxnum" 'BEGIN{printf "%.0f", n}')"
                fi
            fi
        fi
    fi

    # ---------- SNAPSHOT beban RAM saat ini ---------------------------------
    if [ -r /proc/meminfo ]; then
        mt_kb="$(grep -i '^MemTotal:' /proc/meminfo | awk '{print $2}')"
        ma_kb="$(grep -i '^MemAvailable:' /proc/meminfo | awk '{print $2}')"
        if [ -n "$mt_kb" ] && [ -n "$ma_kb" ] && [ "$mt_kb" -gt 0 ]; then
            used_kb=$(( mt_kb - ma_kb ))
            ugb="$(awk -v u="$used_kb" 'BEGIN{printf "%.1f", u/1048576}')"
            upct="$(awk -v u="$used_kb" -v t="$mt_kb" 'BEGIN{printf "%.0f", (u/t)*100}')"
            set_param "ram_usage_gb" "$ugb"
            PARAM_KEYS+=("ram_usage_pct"); PARAM_VALS+=("$upct")
        fi
    fi

    # ---------- SNAPSHOT beban CPU saat ini (delta /proc/stat ~2s) ----------
    if [ -r /proc/stat ]; then
        cpu_line1="$(grep -m1 '^cpu ' /proc/stat)"
        sleep 2
        cpu_line2="$(grep -m1 '^cpu ' /proc/stat)"
        cpu_pct="$(awk -v l1="$cpu_line1" -v l2="$cpu_line2" 'BEGIN{
            n1=split(l1,a," "); n2=split(l2,b," ");
            t1=0; for(i=2;i<=n1;i++) t1+=a[i]; idle1=a[5]+a[6];
            t2=0; for(i=2;i<=n2;i++) t2+=b[i]; idle2=b[5]+b[6];
            dt=t2-t1; di=idle2-idle1;
            if(dt>0){ v=(1-di/dt)*100; if(v<0)v=0; if(v>100)v=100; printf "%.0f", v }
        }')"
        [ -n "$cpu_pct" ] && { PARAM_KEYS+=("cpu_usage_pct"); PARAM_VALS+=("$cpu_pct"); }
    fi

    # ---------- Disk fisik: SSD/HDD + NVMe/SATA -----------------------------
    if command -v lsblk >/dev/null 2>&1; then
        ssd_bytes=0; hdd_bytes=0; ssd_type=""
        # NAME TYPE SIZE(bytes) ROTA TRAN
        while read -r name dtype size rota tran; do
            [ "$dtype" = "disk" ] || continue
            [ -z "$size" ] && continue
            case "$name" in
                loop*|ram*|sr*) continue ;;
            esac
            if [ "$rota" = "0" ]; then
                ssd_bytes=$(( ssd_bytes + size ))
                if printf '%s' "$tran" | grep -qi 'nvme' || printf '%s' "$name" | grep -qi 'nvme'; then
                    ssd_type="NVMe"
                elif [ -z "$ssd_type" ]; then
                    ssd_type="SATA"
                fi
            else
                hdd_bytes=$(( hdd_bytes + size ))
            fi
        done < <(lsblk -b -d -n -o NAME,TYPE,SIZE,ROTA,TRAN 2>/dev/null)

        if [ "$ssd_bytes" -gt 0 ]; then
            set_param "ssd_gb" "$(awk -v b="$ssd_bytes" 'BEGIN{printf "%.0f", b/1073741824}')"
            [ -n "$ssd_type" ] && set_param "ssd_type" "$ssd_type"
        fi
        if [ "$hdd_bytes" -gt 0 ]; then
            set_param "hdd_gb" "$(awk -v b="$hdd_bytes" 'BEGIN{printf "%.0f", b/1073741824}')"
        fi
    fi

    # ---------- Kesehatan disk (best-effort via smartctl) -------------------
    # Hanya bila smartctl tersedia & dapat membaca disk sistem; jangan error.
    if command -v smartctl >/dev/null 2>&1; then
        # Tentukan device disk yang memuat root (/)
        rootsrc="$(df / 2>/dev/null | tail -1 | awk '{print $1}')"
        # /dev/nvme0n1p2 -> /dev/nvme0n1 ; /dev/sda1 -> /dev/sda
        rootdev="$(printf '%s' "$rootsrc" | sed -E 's/p?[0-9]+$//')"
        if [ -n "$rootdev" ] && [ -b "$rootdev" ]; then
            sm_h="$(smartctl -H "$rootdev" 2>/dev/null)"
            if printf '%s' "$sm_h" | grep -qiE 'PASSED|OK'; then
                set_param "disk_health_pct" "100"
                set_param "disk_health_raw" "Healthy"
            elif printf '%s' "$sm_h" | grep -qiE 'FAILED'; then
                set_param "disk_health_pct" "20"
                set_param "disk_health_raw" "Unhealthy"
            fi
        fi
    fi

    # ---------- OS ----------------------------------------------------------
    osname=""
    if [ -r /etc/os-release ]; then
        osname="$(. /etc/os-release 2>/dev/null; printf '%s' "${PRETTY_NAME:-$NAME}")"
    fi
    [ -z "$osname" ] && osname="$(uname -s) $(uname -r)"
    set_param "os" "$osname"

    # ---------- Kapasitas partisi root (/) ----------------------------------
    df_root="$(df -kP / 2>/dev/null | tail -1)"
    if [ -n "$df_root" ]; then
        total_kb="$(printf '%s' "$df_root" | awk '{print $2}')"
        avail_kb="$(printf '%s' "$df_root" | awk '{print $4}')"
        [ -n "$total_kb" ] && set_param "os_total_gb" "$(awk -v k="$total_kb" 'BEGIN{printf "%.0f", k/1048576}')"
        [ -n "$avail_kb" ] && set_param "os_free_gb"  "$(awk -v k="$avail_kb" 'BEGIN{printf "%.0f", k/1048576}')"
    fi

    # ---------- Baterai (persen + Wh) ---------------------------------------
    for bat in /sys/class/power_supply/BAT*; do
        [ -d "$bat" ] || continue
        if [ -r "$bat/capacity" ]; then
            set_param "battery_pct" "$(cat "$bat/capacity" 2>/dev/null)"
        fi
        # Energy (uWh) -> Wh; jika tidak ada pakai charge (uAh) * voltage
        if [ -r "$bat/energy_full" ]; then
            ef="$(cat "$bat/energy_full" 2>/dev/null)"
            [ -n "$ef" ] && [ "$ef" -gt 0 ] && \
                set_param "battery_wh_full" "$(awk -v u="$ef" 'BEGIN{printf "%.1f", u/1000000}')"
        fi
        if [ -r "$bat/energy_full_design" ]; then
            ed="$(cat "$bat/energy_full_design" 2>/dev/null)"
            [ -n "$ed" ] && [ "$ed" -gt 0 ] && \
                set_param "battery_wh_design" "$(awk -v u="$ed" 'BEGIN{printf "%.1f", u/1000000}')"
        fi
        # Fallback charge_full (uAh) * voltage (uV) -> Wh
        if ! has_param "battery_wh_full" && [ -r "$bat/charge_full" ] && [ -r "$bat/voltage_min_design" ]; then
            cf="$(cat "$bat/charge_full" 2>/dev/null)"
            vd="$(cat "$bat/voltage_min_design" 2>/dev/null)"
            if [ -n "$cf" ] && [ -n "$vd" ] && [ "$cf" -gt 0 ] && [ "$vd" -gt 0 ]; then
                set_param "battery_wh_full" "$(awk -v c="$cf" -v v="$vd" 'BEGIN{printf "%.1f", (c/1000000)*(v/1000000)}')"
            fi
        fi
        if ! has_param "battery_wh_design" && [ -r "$bat/charge_full_design" ] && [ -r "$bat/voltage_min_design" ]; then
            cfd="$(cat "$bat/charge_full_design" 2>/dev/null)"
            vd="$(cat "$bat/voltage_min_design" 2>/dev/null)"
            if [ -n "$cfd" ] && [ -n "$vd" ] && [ "$cfd" -gt 0 ] && [ "$vd" -gt 0 ]; then
                set_param "battery_wh_design" "$(awk -v c="$cfd" -v v="$vd" 'BEGIN{printf "%.1f", (c/1000000)*(v/1000000)}')"
            fi
        fi
        break
    done

elif [ "$OS" = "Darwin" ]; then
    # =====================  macOS  =========================================
    HW="$(system_profiler SPHardwareDataType 2>/dev/null)"

    # ---------- MAC address (interface aktif) -------------------------------
    mac=""
    active_if="$(route get default 2>/dev/null | awk '/interface:/{print $2}')"
    if [ -n "$active_if" ]; then
        mac="$(ifconfig "$active_if" 2>/dev/null | awk '/ether/{print $2; exit}')"
    fi
    if [ -z "$mac" ]; then
        mac="$(ifconfig en0 2>/dev/null | awk '/ether/{print $2; exit}')"
    fi
    [ -n "$mac" ] && set_param "mac" "$(printf '%s' "$mac" | tr '[:lower:]' '[:upper:]')"

    # ---------- Serial / brand / model --------------------------------------
    serial="$(printf '%s\n' "$HW" | awk -F': ' '/Serial Number/{print $2; exit}')"
    [ -n "$serial" ] && set_param "serial" "$serial"
    set_param "brand" "Apple"
    model="$(printf '%s\n' "$HW" | awk -F': ' '/Model Name/{print $2; exit}')"
    [ -z "$model" ] && model="$(sysctl -n hw.model 2>/dev/null)"
    [ -n "$model" ] && set_param "model" "$model"

    # ---------- CPU ---------------------------------------------------------
    cpu="$(sysctl -n machdep.cpu.brand_string 2>/dev/null)"
    if [ -z "$cpu" ]; then
        # Apple Silicon: ambil dari system_profiler
        cpu="$(printf '%s\n' "$HW" | awk -F': ' '/Chip|Processor Name/{print $2; exit}')"
    fi
    [ -n "$cpu" ] && set_param "cpu" "$cpu"

    cores="$(sysctl -n hw.physicalcpu 2>/dev/null)"
    [ -n "$cores" ] && set_param "cpu_cores" "$cores"
    threads="$(sysctl -n hw.logicalcpu 2>/dev/null)"
    [ -n "$threads" ] && set_param "cpu_threads" "$threads"

    case "$(uname -m)" in
        x86_64) set_param "cpu_arch" "x64" ;;
        arm64|aarch64) set_param "cpu_arch" "arm64" ;;
        i?86) set_param "cpu_arch" "x86" ;;
    esac

    # Kecepatan CPU (Hz -> MHz); Apple Silicon biasanya tidak menyediakan
    cpufreq="$(sysctl -n hw.cpufrequency_max 2>/dev/null || sysctl -n hw.cpufrequency 2>/dev/null)"
    if [ -n "$cpufreq" ] && [ "$cpufreq" -gt 0 ] 2>/dev/null; then
        set_param "cpu_speed_mhz" "$(awk -v h="$cpufreq" 'BEGIN{printf "%.0f", h/1000000}')"
    fi

    # ---------- GPU ---------------------------------------------------------
    gpu="$(system_profiler SPDisplaysDataType 2>/dev/null | awk -F': ' '/Chipset Model/{print $2}' | paste -sd ', ' -)"
    [ -n "$gpu" ] && set_param "gpu" "$gpu"

    # ---------- RAM total ---------------------------------------------------
    membytes="$(sysctl -n hw.memsize 2>/dev/null)"
    if [ -n "$membytes" ] && [ "$membytes" -gt 0 ]; then
        set_param "ram_gb" "$(awk -v b="$membytes" 'BEGIN{printf "%.0f", b/1073741824}')"
    fi

    # ---------- RAM tipe & kecepatan ----------------------------------------
    MEMINFO="$(system_profiler SPMemoryDataType 2>/dev/null)"
    if [ -n "$MEMINFO" ]; then
        rtype="$(printf '%s\n' "$MEMINFO" | awk -F': ' '/Type:/{print $2; exit}')"
        [ -n "$rtype" ] && set_param "ram_type" "$rtype"
        rspeed="$(printf '%s\n' "$MEMINFO" | awk -F': ' '/Speed:/{print $2; exit}' | grep -oE '[0-9]+' | head -1)"
        [ -n "$rspeed" ] && set_param "ram_speed_mhz" "$rspeed"
    fi
    # Apple Silicon: tipe memori sering "LPDDR" via SPHardwareDataType
    if ! has_param "ram_type"; then
        rtype2="$(printf '%s\n' "$HW" | awk -F': ' '/Memory:/{print $2}' | grep -oiE 'LPDDR[0-9]+|DDR[0-9]+' | head -1)"
        [ -n "$rtype2" ] && set_param "ram_type" "$rtype2"
    fi

    # ---------- SNAPSHOT beban RAM saat ini ---------------------------------
    if command -v vm_stat >/dev/null 2>&1 && [ -n "$membytes" ]; then
        page_size="$(vm_stat 2>/dev/null | sed -n 's/.*page size of \([0-9]*\) bytes.*/\1/p')"
        [ -z "$page_size" ] && page_size=4096
        # Memori terpakai = total - (free + inactive)  [pendekatan]
        free_pages="$(vm_stat 2>/dev/null | awk '/Pages free/{gsub(/\./,"",$3); print $3}')"
        inactive_pages="$(vm_stat 2>/dev/null | awk '/Pages inactive/{gsub(/\./,"",$3); print $3}')"
        spec_pages="$(vm_stat 2>/dev/null | awk '/Pages speculative/{gsub(/\./,"",$3); print $3}')"
        free_pages="${free_pages:-0}"; inactive_pages="${inactive_pages:-0}"; spec_pages="${spec_pages:-0}"
        avail_bytes=$(( (free_pages + inactive_pages + spec_pages) * page_size ))
        used_bytes=$(( membytes - avail_bytes ))
        [ "$used_bytes" -lt 0 ] && used_bytes=0
        set_param "ram_usage_gb" "$(awk -v u="$used_bytes" 'BEGIN{printf "%.1f", u/1073741824}')"
        upct="$(awk -v u="$used_bytes" -v t="$membytes" 'BEGIN{printf "%.0f", (u/t)*100}')"
        PARAM_KEYS+=("ram_usage_pct"); PARAM_VALS+=("$upct")
    fi

    # ---------- SNAPSHOT beban CPU saat ini ---------------------------------
    # `top -l 2` mengambil 2 sampel (jeda ~1s); sampel kedua akurat. Ambil % idle
    # dari baris "CPU usage", beban = 100 - idle.
    if command -v top >/dev/null 2>&1; then
        cpu_idle="$(top -l 2 -n 0 2>/dev/null | grep -E '^CPU usage' | tail -1 | grep -oE '[0-9.]+% idle' | grep -oE '[0-9.]+' | head -1)"
        if [ -n "$cpu_idle" ]; then
            cpu_pct="$(awk -v idle="$cpu_idle" 'BEGIN{ v=100-idle; if(v<0)v=0; if(v>100)v=100; printf "%.0f", v }')"
            PARAM_KEYS+=("cpu_usage_pct"); PARAM_VALS+=("$cpu_pct")
        fi
    fi

    # ---------- Disk fisik (storage internal) -------------------------------
    STOR="$(system_profiler SPNVMeDataType SPSerialATADataType 2>/dev/null)"
    if [ -n "$STOR" ]; then
        # Total kapasitas SSD (perkiraan; semua Mac modern = SSD)
        cap="$(printf '%s\n' "$STOR" | grep -iE 'Capacity:' | head -1 | grep -oE '[0-9.]+ *[TG]B' | head -1)"
        if [ -n "$cap" ]; then
            num="$(printf '%s' "$cap" | grep -oE '[0-9.]+')"
            unit="$(printf '%s' "$cap" | grep -oiE '[TG]B')"
            if printf '%s' "$unit" | grep -qi 'TB'; then
                set_param "ssd_gb" "$(awk -v n="$num" 'BEGIN{printf "%.0f", n*1000}')"
            else
                set_param "ssd_gb" "$(awk -v n="$num" 'BEGIN{printf "%.0f", n}')"
            fi
        fi
        # Tipe: NVMe vs SATA
        if printf '%s' "$STOR" | grep -qi 'NVMe'; then
            set_param "ssd_type" "NVMe"
        elif printf '%s' "$STOR" | grep -qi 'SATA'; then
            set_param "ssd_type" "SATA"
        fi
    fi

    # ---------- OS ----------------------------------------------------------
    prodname="$(sw_vers -productName 2>/dev/null)"
    prodver="$(sw_vers -productVersion 2>/dev/null)"
    if [ -n "$prodname" ]; then
        set_param "os" "$(printf '%s %s' "$prodname" "$prodver" | sed 's/ *$//')"
    else
        set_param "os" "macOS"
    fi

    # ---------- Kapasitas partisi root (/) ----------------------------------
    df_root="$(df -kP / 2>/dev/null | tail -1)"
    if [ -n "$df_root" ]; then
        total_kb="$(printf '%s' "$df_root" | awk '{print $2}')"
        avail_kb="$(printf '%s' "$df_root" | awk '{print $4}')"
        [ -n "$total_kb" ] && set_param "os_total_gb" "$(awk -v k="$total_kb" 'BEGIN{printf "%.0f", k/1048576}')"
        [ -n "$avail_kb" ] && set_param "os_free_gb"  "$(awk -v k="$avail_kb" 'BEGIN{printf "%.0f", k/1048576}')"
    fi

    # ---------- Baterai -----------------------------------------------------
    if command -v pmset >/dev/null 2>&1; then
        bpct="$(pmset -g batt 2>/dev/null | grep -oE '[0-9]+%' | head -1 | tr -d '%')"
        [ -n "$bpct" ] && set_param "battery_pct" "$bpct"
    fi
    # Kapasitas Wh dari ioreg (mAh * voltage). AppleSmartBattery menyimpan mAh.
    if command -v ioreg >/dev/null 2>&1; then
        ioreg_batt="$(ioreg -r -c AppleSmartBattery 2>/dev/null)"
        if [ -n "$ioreg_batt" ]; then
            volt_mv="$(printf '%s\n' "$ioreg_batt" | grep -oE '"Voltage" *= *[0-9]+' | grep -oE '[0-9]+' | head -1)"
            full_mah="$(printf '%s\n' "$ioreg_batt" | grep -oE '"AppleRawMaxCapacity" *= *[0-9]+' | grep -oE '[0-9]+' | head -1)"
            [ -z "$full_mah" ] && full_mah="$(printf '%s\n' "$ioreg_batt" | grep -oE '"MaxCapacity" *= *[0-9]+' | grep -oE '[0-9]+' | head -1)"
            design_mah="$(printf '%s\n' "$ioreg_batt" | grep -oE '"DesignCapacity" *= *[0-9]+' | grep -oE '[0-9]+' | head -1)"
            if [ -n "$volt_mv" ] && [ -n "$full_mah" ] && [ "$volt_mv" -gt 0 ]; then
                set_param "battery_wh_full" "$(awk -v m="$full_mah" -v v="$volt_mv" 'BEGIN{printf "%.1f", (m/1000)*(v/1000)}')"
            fi
            if [ -n "$volt_mv" ] && [ -n "$design_mah" ] && [ "$volt_mv" -gt 0 ]; then
                set_param "battery_wh_design" "$(awk -v m="$design_mah" -v v="$volt_mv" 'BEGIN{printf "%.1f", (m/1000)*(v/1000)}')"
            fi
        fi
    fi
fi

# ============================================================================
#  BANGUN URL & BUKA BROWSER
# ============================================================================
query=""
i=0
while [ "$i" -lt "${#PARAM_KEYS[@]}" ]; do
    k="${PARAM_KEYS[$i]}"
    v="$(urlencode "${PARAM_VALS[$i]}")"
    if [ -z "$query" ]; then
        query="$k=$v"
    else
        query="$query&$k=$v"
    fi
    i=$(( i + 1 ))
done

url="$SERVER_BASE_URL/form?$query"

echo ""
echo "Spesifikasi terdeteksi (${#PARAM_KEYS[@]} data):"
i=0
while [ "$i" -lt "${#PARAM_KEYS[@]}" ]; do
    printf '  %-18s: %s\n' "${PARAM_KEYS[$i]}" "${PARAM_VALS[$i]}"
    i=$(( i + 1 ))
done

echo ""
echo "URL form:"
echo "$url"
echo ""
echo "Membuka form di browser..."

opened=1
if [ "$OS" = "Darwin" ]; then
    open "$url" >/dev/null 2>&1 && opened=0
elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$url" >/dev/null 2>&1 && opened=0
fi

if [ "$opened" -eq 0 ]; then
    echo "Browser dibuka. Silakan lengkapi data diri Anda pada form, lalu klik Kirim."
else
    echo "Tidak bisa membuka browser otomatis. Salin & buka URL di atas secara manual."
fi
