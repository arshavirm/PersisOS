#!/bin/bash
# ============================================================================
# PersisOS Build Script
# Simple bash script to build a Debian-based live ISO
# ============================================================================
# Usage: sudo ./build.sh [config_file]
# Example: sudo ./build.sh build.conf
# ============================================================================

set -euo pipefail

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="${SCRIPT_DIR}"

# Load configuration
CONFIG_FILE="${1:-${BASE_DIR}/build.conf}"

if [[ ! -f "${CONFIG_FILE}" ]]; then
    echo "[ERROR] Configuration file not found: ${CONFIG_FILE}"
    exit 1
fi

echo "[INFO] Loading configuration from: ${CONFIG_FILE}"
source "${CONFIG_FILE}"

# Resolve paths relative to config file location
CONFIG_DIR="$(dirname "${CONFIG_FILE}")"
resolve_path() {
    local path="$1"
    if [[ "${path}" == /* ]]; then
        echo "${path}"
    else
        echo "${CONFIG_DIR}/${path}"
    fi
}

ASSETS_DIR="$(resolve_path "${ASSETS_DIR}")"
ROOTFS_DIR="$(resolve_path "${ROOTFS_DIR}")"
LIVE_DIR="$(resolve_path "${LIVE_DIR}")"
ISO_WORK_DIR="$(resolve_path "${ISO_WORK_DIR}")"
OUTPUT_DIR="$(resolve_path "${OUTPUT_DIR}")"

# Export variables for hooks
export BASE_DIR CONFIG_DIR ASSETS_DIR ROOTFS_DIR LIVE_DIR ISO_WORK_DIR OUTPUT_DIR
export DISTRO_NAME DISTRO_VERSION DISTRO_HOSTNAME
export DEBIAN_DIST DEBIAN_ARCH DEBIAN_MIRROR DEBIAN_COMPONENTS

# ============================================================================
# Helper Functions
# ============================================================================

log() {
    echo "[INFO] $*"
}

die() {
    echo "[ERROR] $*" >&2
    exit 1
}

run() {
    log "$*"
    "$@"
}

is_mounted() {
    mountpoint -q "$1" 2>/dev/null
}

cleanup_mounts() {
    local rootfs="$1"
    for m in dev/pts dev proc sys run; do
        local target="${rootfs}/${m}"
        if is_mounted "${target}"; then
            log "Unmounting ${target}"
            umount -lf "${target}" 2>/dev/null || true
        fi
    done
}

# ============================================================================
# File Copying Function
# ============================================================================

copy_asset_files() {
    log "Copying asset files..."
    
    # Backgrounds
    if [[ -d "${ASSETS_DIR}/backgrounds" ]]; then
        mkdir -p "${ROOTFS_DIR}/usr/share/backgrounds/persisos"
        cp -r "${ASSETS_DIR}/backgrounds/"* "${ROOTFS_DIR}/usr/share/backgrounds/persisos/"
    fi
    
    # SVG icons
    if [[ -f "${BASE_DIR}/persisos.svg" ]]; then
        mkdir -p "${ROOTFS_DIR}/usr/share/pixmaps/persisos"
        cp "${BASE_DIR}/persisos.svg" "${ROOTFS_DIR}/usr/share/pixmaps/persisos/persisos.svg"
        cp "${BASE_DIR}/persisos.svg" "${ROOTFS_DIR}/usr/share/pixmaps/persisos.svg"
    fi
    
    # OS release files
    if [[ -f "${ASSETS_DIR}/os-release" ]]; then
        mkdir -p "${ROOTFS_DIR}/etc"
        mkdir -p "${ROOTFS_DIR}/usr/lib"
        cp "${ASSETS_DIR}/os-release" "${ROOTFS_DIR}/etc/os-release"
        cp "${ASSETS_DIR}/os-release" "${ROOTFS_DIR}/usr/lib/os-release"
    fi
    
    # Plymouth theme
    if [[ -d "${ASSETS_DIR}/plymouth/persisos" ]]; then
        mkdir -p "${ROOTFS_DIR}/usr/share/plymouth/themes"
        cp -r "${ASSETS_DIR}/plymouth/persisos" "${ROOTFS_DIR}/usr/share/plymouth/themes/"
    fi
    
    # Face icon
    if [[ -f "${ASSETS_DIR}/.face" ]]; then
        mkdir -p "${ROOTFS_DIR}/etc/skel"
        mkdir -p "${ROOTFS_DIR}/root"
        cp "${ASSETS_DIR}/.face" "${ROOTFS_DIR}/etc/skel/.face"
        cp "${ASSETS_DIR}/.face" "${ROOTFS_DIR}/root/.face"
    fi
}

copy_calamares_files() {
    log "Copying Calamares installer files..."
    
    # Calamares branding
    if [[ -d "${ASSETS_DIR}/calamares/persisos" ]]; then
        mkdir -p "${ROOTFS_DIR}/etc/calamares/branding"
        cp -r "${ASSETS_DIR}/calamares/persisos" "${ROOTFS_DIR}/etc/calamares/branding/"
    fi
    
    # Calamares configuration
    for conf_file in settings.conf packages.conf packagechooser.conf; do
        if [[ -f "${ASSETS_DIR}/calamares/${conf_file}" ]]; then
            local dest_dir="etc/calamares"
            [[ "${conf_file}" != "settings.conf" ]] && dest_dir="etc/calamares/modules"
            mkdir -p "${ROOTFS_DIR}/${dest_dir}"
            cp "${ASSETS_DIR}/calamares/${conf_file}" "${ROOTFS_DIR}/${dest_dir}/${conf_file}"
        fi
    done
    
    # Desktop file
    if [[ -f "${ASSETS_DIR}/calamares-install-persisos.desktop" ]]; then
        mkdir -p "${ROOTFS_DIR}/usr/share/applications"
        cp "${ASSETS_DIR}/calamares-install-persisos.desktop" "${ROOTFS_DIR}/usr/share/applications/"
    fi
    
    # First login script
    if [[ -f "${ASSETS_DIR}/persisos-first-login" ]]; then
        mkdir -p "${ROOTFS_DIR}/usr/local/bin"
        cp "${ASSETS_DIR}/persisos-first-login" "${ROOTFS_DIR}/usr/local/bin/"
        chmod 755 "${ROOTFS_DIR}/usr/local/bin/persisos-first-login"
    fi
    
    # GRUB config
    if [[ -f "${ASSETS_DIR}/grub.cfg" ]]; then
        mkdir -p "${ROOTFS_DIR}/boot/grub"
        cp "${ASSETS_DIR}/grub.cfg" "${ROOTFS_DIR}/boot/grub/grub.cfg"
    fi
}

# ============================================================================
# Write System Configuration Files
# ============================================================================

write_system_configs() {
    log "Writing system configuration files..."
    
    # Hostname
    echo "${DISTRO_HOSTNAME}" > "${ROOTFS_DIR}/etc/hostname"
    
    # Hosts file
    cat > "${ROOTFS_DIR}/etc/hosts" <<EOF
127.0.0.1	localhost
127.0.1.1	${DISTRO_HOSTNAME}
EOF
    
    # Network interfaces
    cat > "${ROOTFS_DIR}/etc/network/interfaces" <<EOF
auto lo
iface lo inet loopback
EOF
    
    # APT parallel downloads
    cat > "${ROOTFS_DIR}/etc/apt/apt.conf.d/99parallel" <<EOF
Acquire::Queue-Host-Limit "6";
Acquire::http::Pipeline-Depth "10";
EOF
    
    # NetworkManager managed devices
    mkdir -p "${ROOTFS_DIR}/etc/NetworkManager/conf.d"
    cat > "${ROOTFS_DIR}/etc/NetworkManager/conf.d/10-globally-managed-devices.conf" <<EOF
[ifupdown]
managed=true
EOF
    
    # NetworkManager rfkill unblock
    mkdir -p "${ROOTFS_DIR}/etc/systemd/system/NetworkManager.service.d"
    cat > "${ROOTFS_DIR}/etc/systemd/system/NetworkManager.service.d/10-rfkill-unblock.conf" <<EOF
[Service]
ExecStartPre=/usr/sbin/rfkill unblock all
EOF
    
    # GRUB defaults
    local grub_file="${ROOTFS_DIR}/etc/default/grub"
    if [[ -f "${grub_file}" ]]; then
        # Update existing GRUB config
        local temp_file=$(mktemp)
        while IFS= read -r line || [[ -n "$line" ]]; do
            case "$line" in
                GRUB_BACKGROUND=*)
                    echo "GRUB_BACKGROUND=\"${GRUB_BACKGROUND}\"" >> "${temp_file}"
                    ;;
                GRUB_TERMINAL_OUTPUT=*)
                    echo "GRUB_TERMINAL_OUTPUT=\"${GRUB_TERMINAL_OUTPUT}\"" >> "${temp_file}"
                    ;;
                GRUB_GFXMODE=*)
                    echo "GRUB_GFXMODE=\"${GRUB_GFXMODE}\"" >> "${temp_file}"
                    ;;
                *)
                    echo "${line}" >> "${temp_file}"
                    ;;
            esac
        done < "${grub_file}"
        
        # Add missing entries
        grep -q "^GRUB_BACKGROUND=" "${temp_file}" || echo "GRUB_BACKGROUND=\"${GRUB_BACKGROUND}\"" >> "${temp_file}"
        grep -q "^GRUB_TERMINAL_OUTPUT=" "${temp_file}" || echo "GRUB_TERMINAL_OUTPUT=\"${GRUB_TERMINAL_OUTPUT}\"" >> "${temp_file}"
        grep -q "^GRUB_GFXMODE=" "${temp_file}" || echo "GRUB_GFXMODE=\"${GRUB_GFXMODE}\"" >> "${temp_file}"
        
        mv "${temp_file}" "${grub_file}"
    fi
}

# ============================================================================
# STAGE 1: Build rootfs with debootstrap
# ============================================================================

stage_build_rootfs() {
    log "=== Stage 1: Building rootfs ==="
    
    # Check assets directory
    if [[ ! -d "${ASSETS_DIR}" ]]; then
        die "Assets directory not found: ${ASSETS_DIR}"
    fi
    
    # Run pre-rootfs hook
    hook_before_rootfs
    
    # Clean existing rootfs
    if [[ -d "${ROOTFS_DIR}" ]]; then
        log "Removing existing rootfs..."
        cleanup_mounts "${ROOTFS_DIR}"
        rm -rf "${ROOTFS_DIR}"
    fi
    
    mkdir -p "${ROOTFS_DIR}"
    
    # Run debootstrap
    log "Running debootstrap for ${DEBIAN_DIST}/${DEBIAN_ARCH}..."
    run debootstrap \
        --arch="${DEBIAN_ARCH}" \
        "${DEBIAN_DIST}" \
        "${ROOTFS_DIR}" \
        "${DEBIAN_MIRROR}"
    
    # Run post-debootstrap hook
    hook_after_debootstrap
    
    # Mount virtual filesystems
    log "Mounting virtual filesystems..."
    mkdir -p "${ROOTFS_DIR}/dev/pts"
    mkdir -p "${ROOTFS_DIR}/proc"
    mkdir -p "${ROOTFS_DIR}/sys"
    mkdir -p "${ROOTFS_DIR}/run"
    
    run mount --bind /dev "${ROOTFS_DIR}/dev"
    run mount --bind /dev/pts "${ROOTFS_DIR}/dev/pts"
    run mount -t proc proc "${ROOTFS_DIR}/proc"
    run mount -t sysfs sys "${ROOTFS_DIR}/sys"
    run mount -t tmpfs tmpfs "${ROOTFS_DIR}/run"
    
    # Copy before-chroot files
    copy_asset_files
    
    # Write system configs
    write_system_configs
    
    # Run before-chroot hook
    hook_before_chroot
    
    # ========================================================================
    # Chroot operations
    # ========================================================================
    log "Running chroot setup (installing packages, configuring system)..."
    
    # Create chroot script
    local chroot_script="${ROOTFS_DIR}/root/chroot.sh"
    
    cat > "${chroot_script}" <<'CHROOT_START'
#!/bin/bash
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

CHROOT_START
    
    # Setup apt sources
    cat >> "${chroot_script}" <<EOF
# Configure apt sources
cat > /etc/apt/sources.list <<'APT_SOURCES'
deb ${DEBIAN_MIRROR} ${DEBIAN_DIST} ${DEBIAN_COMPONENTS}
APT_SOURCES

EOF
    
    # Add extra apt sources if defined
    if [[ -n "${EXTRA_APT_SOURCES}" ]]; then
        echo "${EXTRA_APT_SOURCES}" >> "${chroot_script}"
    fi
    
    # Run chroot hook after sources
    cat >> "${chroot_script}" <<'CHROOT_HOOK'
# Run chroot hook after sources
CHROOT_HOOK
    
    # We'll execute the chroot hook function by sourcing it later
    
    # apt-get update
    echo "apt-get update" >> "${chroot_script}"
    echo "" >> "${chroot_script}"
    
    # Install packages
    if [[ ${#PACKAGES[@]} -gt 0 ]]; then
        echo "apt-get install -y \\" >> "${chroot_script}"
        for i in "${!PACKAGES[@]}"; do
            if [[ $i -eq $((${#PACKAGES[@]} - 1)) ]]; then
                echo "    ${PACKAGES[$i]}" >> "${chroot_script}"
            else
                echo "    ${PACKAGES[$i]} \\" >> "${chroot_script}"
            fi
        done
        echo "" >> "${chroot_script}"
    fi
    
    # Locale setup
    cat >> "${chroot_script}" <<'LOCALE_SETUP'
# Locale setup
sed -i 's/^# *en_US.UTF-8 UTF-8/en_US.UTF-8 UTF-8/' /etc/locale.gen
locale-gen
update-locale LANG=en_US.UTF-8

LOCALE_SETUP
    
    # User accounts
    for user_entry in "${USERS[@]}"; do
        IFS=':' read -r username password shell groups create_home <<< "${user_entry}"
        
        local user_cmd="useradd --shell ${shell}"
        [[ "${create_home}" == "yes" ]] && user_cmd+=" --create-home"
        [[ -n "${groups}" ]] && user_cmd+=" --groups ${groups}"
        user_cmd+=" ${username}"
        
        echo "${user_cmd}" >> "${chroot_script}"
        echo "echo '${username}:${password}' | chpasswd" >> "${chroot_script}"
    done
    
    # Root password
    echo "echo 'root:${ROOT_PASSWORD}' | chpasswd" >> "${chroot_script}"
    echo "" >> "${chroot_script}"
    
    # Enable services
    for svc in "${SERVICES[@]}"; do
        echo "systemctl enable ${svc}" >> "${chroot_script}"
    done
    echo "" >> "${chroot_script}"
    
    # Plymouth theme
    if [[ -n "${PLYMOUTH_THEME}" ]]; then
        echo "plymouth-set-default-theme -R ${PLYMOUTH_THEME} || true" >> "${chroot_script}"
    fi
    
    echo "update-desktop-database /usr/share/applications || true" >> "${chroot_script}"
    echo "" >> "${chroot_script}"
    
    # Finalization
    [[ "${MACHINE_ID_SETUP}" == "yes" ]] && echo "systemd-machine-id-setup" >> "${chroot_script}"
    [[ "${APT_AUTOREMOVE}" == "yes" ]] && echo "apt-get autoremove -y" >> "${chroot_script}"
    [[ "${APT_CLEAN}" == "yes" ]] && echo "apt-get clean" >> "${chroot_script}"
    [[ "${UPDATE_INITRAMFS}" == "yes" ]] && echo "update-initramfs -u -k all" >> "${chroot_script}"
    
    # Make script executable and run it
    chmod 755 "${chroot_script}"
    
    # Execute chroot script with inline hook execution
    cat > "${ROOTFS_DIR}/root/run_chroot.sh" <<RUN_CHROOT
#!/bin/bash
set -euo pipefail

# Source the main chroot script
bash /root/chroot.sh

# Run chroot hooks
$(declare -f chroot_hook_after_sources 2>/dev/null && echo "chroot_hook_after_sources" || echo ":")
$(declare -f chroot_hook_after_update 2>/dev/null && echo "chroot_hook_after_update" || echo ":")
$(declare -f chroot_hook_after_packages 2>/dev/null && echo "chroot_hook_after_packages" || echo ":")
RUN_CHROOT
    
    chmod 755 "${ROOTFS_DIR}/root/run_chroot.sh"
    run chroot "${ROOTFS_DIR}" /bin/bash /root/run_chroot.sh
    
    # Cleanup chroot scripts
    rm -f "${chroot_script}" "${ROOTFS_DIR}/root/run_chroot.sh"
    
    # Run after-chroot hook
    hook_after_chroot
    
    # Copy Calamares files (after chroot)
    copy_calamares_files
    
    # Cleanup glob patterns
    for pattern in "usr/share/applications/calamares*.desktop" "etc/xdg/autostart/calamares*.desktop"; do
        find "${ROOTFS_DIR}/${pattern}" -type f -delete 2>/dev/null || true
    done
    
    # Unmount
    log "Unmounting rootfs..."
    cleanup_mounts "${ROOTFS_DIR}"
    
    # Run after-rootfs hook
    hook_after_rootfs
    
    log "Rootfs build complete!"
}

# ============================================================================
# STAGE 2: Create live filesystem (SquashFS)
# ============================================================================

stage_create_live() {
    log "=== Stage 2: Creating live filesystem ==="
    
    if [[ ! -d "${ROOTFS_DIR}" ]]; then
        die "Rootfs not found at ${ROOTFS_DIR}"
    fi
    
    # Run before-live hook
    hook_before_live
    
    # Clean live directory
    rm -rf "${LIVE_DIR}"
    mkdir -p "${LIVE_DIR}/live"
    
    # Clean rootfs caches
    log "Cleaning rootfs caches..."
    rm -rf "${ROOTFS_DIR}/tmp"
    mkdir -p "${ROOTFS_DIR}/tmp"
    rm -f "${ROOTFS_DIR}/var/cache/apt/archives/"*.deb 2>/dev/null || true
    echo "" > "${ROOTFS_DIR}/etc/machine-id"
    
    # Create SquashFS
    log "Creating SquashFS (${SQUASHFS_COMP}, block=${SQUASHFS_BLOCK_SIZE})..."
    run mksquashfs \
        "${ROOTFS_DIR}" \
        "${LIVE_DIR}/live/filesystem.squashfs" \
        -comp "${SQUASHFS_COMP}" \
        -b "${SQUASHFS_BLOCK_SIZE}" \
        -wildcards -e "${SQUASHFS_EXCLUDE}"
    
    # Copy kernel
    log "Copying kernel..."
    local kernels=($(ls -t "${ROOTFS_DIR}/boot/vmlinuz-"* 2>/dev/null || true))
    if [[ ${#kernels[@]} -eq 0 ]]; then
        die "No vmlinuz-* found in ${ROOTFS_DIR}/boot"
    fi
    cp "${kernels[0]}" "${LIVE_DIR}/vmlinuz"
    
    # Copy initrd
    log "Copying initrd..."
    local initrds=($(ls -t "${ROOTFS_DIR}/boot/initrd.img-"* 2>/dev/null || true))
    if [[ ${#initrds[@]} -eq 0 ]]; then
        die "No initrd.img-* found in ${ROOTFS_DIR}/boot"
    fi
    cp "${initrds[0]}" "${LIVE_DIR}/initrd"
    
    # Copy memtest if available
    for pattern in "memtest86*.bin" "memtest86*.efi"; do
        local matches=($(ls "${ROOTFS_DIR}/boot/${pattern}" 2>/dev/null || true))
        if [[ ${#matches[@]} -gt 0 ]]; then
            cp "${matches[0]}" "${LIVE_DIR}/$(basename "${matches[0]}")"
        fi
    done
    
    # Run after-live hook
    hook_after_live
    
    log "Live filesystem complete!"
}

# ============================================================================
# STAGE 3: Build bootable ISO
# ============================================================================

stage_build_iso() {
    log "=== Stage 3: Building ISO ==="
    
    local squashfs="${LIVE_DIR}/live/filesystem.squashfs"
    if [[ ! -f "${squashfs}" ]]; then
        die "filesystem.squashfs not found (run stage 2 first)"
    fi
    
    # Run before-iso hook
    hook_before_iso
    
    # Clean ISO work directory
    rm -rf "${ISO_WORK_DIR}"
    mkdir -p "${ISO_WORK_DIR}/boot/grub"
    mkdir -p "${ISO_WORK_DIR}/live"
    mkdir -p "${OUTPUT_DIR}"
    
    # Copy files to ISO tree
    log "Copying files to ISO tree..."
    cp "${squashfs}" "${ISO_WORK_DIR}/live/filesystem.squashfs"
    cp "${LIVE_DIR}/vmlinuz" "${ISO_WORK_DIR}/live/vmlinuz"
    cp "${LIVE_DIR}/initrd" "${ISO_WORK_DIR}/live/initrd"
    
    # Copy memtest if available
    for pattern in "memtest86*.efi" "memtest86*.bin"; do
        for f in "${LIVE_DIR}/${pattern}"; do
            [[ -f "${f}" ]] && cp "${f}" "${ISO_WORK_DIR}/boot/$(basename "${f}")"
        done
    done
    
    # Copy GRUB configuration
    log "Copying GRUB configuration..."
    cp "${ASSETS_DIR}/grub.cfg" "${ISO_WORK_DIR}/boot/grub/grub.cfg"
    
    # Build ISO name
    local iso_name="${DISTRO_NAME}-${DISTRO_VERSION}-${DEBIAN_ARCH}.iso"
    local iso_path="${OUTPUT_DIR}/${iso_name}"
    
    # Build ISO with grub-mkrescue
    log "Building ISO with grub-mkrescue..."
    run grub-mkrescue --compress=xz -o "${iso_path}" "${ISO_WORK_DIR}"
    
    # Run after-iso hook
    hook_after_iso
    
    log "ISO built successfully: ${iso_path}"
}

# ============================================================================
# Main Execution
# ============================================================================

main() {
    # Check if running as root
    if [[ $EUID -ne 0 ]]; then
        die "This script must be run as root"
    fi
    
    # Check required tools
    for tool in debootstrap mksquashfs grub-mkrescue; do
        if ! command -v "${tool}" &>/dev/null; then
            die "Required tool not found: ${tool}"
        fi
    done
    
    # Run all stages
    stage_build_rootfs
    stage_create_live
    stage_build_iso
    
    log "Build process completed successfully!"
}

# Run main function
main "$@"
