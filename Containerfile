FROM quay.io/fedora/fedora-bootc:43

SHELL ["/bin/bash", "-xeuo", "pipefail", "-c"]

# --- Admin user ---
# -U: Creates a group with the same name as the user.
# -G: Adds user to supplementary groups (comma-separated).
# -M: Does not create the home directory.
# -d: Specifies the user's home directory path.
# -s: Sets the login shell for the user.
RUN <<EOR
    useradd -u 1000 -U -G wheel -M -d /dev/null -s /bin/zsh jh
    echo '%wheel ALL=NOPASSWD: ALL' > /etc/sudoers.d/wheel-nopasswd
EOR

# --- System Updates & Tools ---
RUN <<EOR
    dnf -y update
    dnf -y install \
        zsh \
        neovim \
        git \
        btop \
        htop \
        wireshark-cli \
        tcpdump \
        bind-utils \
        ripgrep \
        fd-find \
        tmux \
        firewalld \
        wireguard-tools
    dnf clean all
EOR

# --- SSH key ---
COPY users/jh.pub /usr/ssh/jh.keys

RUN <<EOR
    cat <<EOF >> /etc/ssh/sshd_config.d/30-auth-system.conf
        PasswordAuthentication no
        ChallengeResponseAuthentication no
        PermitRootLogin prohibit-password
        PubkeyAuthentication yes
        AuthorizedKeysFile /usr/ssh/jh.keys
    EOF
    chmod 0600 /usr/ssh/jh.keys
EOR

# --- System configuration (Hostname, Timezone, DNS) ---
RUN <<EOR
    echo "pi1.local" > /etc/hostname
    rm -f /etc/localtime
    ln -s /usr/share/zoneinfo/Europe/Berlin /etc/localtime
    cat <<EOF > /etc/systemd/resolved.conf
        [Resolve]
        DNS=1.1.1.1 8.8.8.8
        DNSStubListener=no
    EOF
EOR

# --- Firewall & Services ---
RUN <<EOR
    systemctl enable podman.socket
    systemctl enable podman-auto-update.timer
    systemctl enable bluetooth.service
    systemctl enable avahi-daemon.service
    firewall-offline-cmd --zone=public --add-service=dns
    firewall-offline-cmd --zone=public --add-service=https
    firewall-offline-cmd --zone=public --add-port=51820/udp
    rm -rf /var/cache/ /var/log/ /var/lib/
EOR

# --- Workloads ---
COPY quadlets/ /etc/containers/systemd/
COPY configs/ /opt/containers/config/

# Secrets cannot be baked into the image - must be decrypted at runtime
# COPY secrets/ /opt/containers/secrets

# --- Transient ---
RUN <<EOR
    echo -e '[etc]\ntransient=true' >> /usr/lib/ostree/prepare-root.conf
    kver=$(cd /usr/lib/modules && echo *); dracut -vf /usr/lib/modules/$kver/initramfs.img $kver
EOR

# --- Linting ---
RUN bootc container lint
