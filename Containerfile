FROM ghcr.io/getsops/sops:v3.13.3 AS sops
FROM quay.io/fedora/fedora-bootc:45
COPY --from=sops /usr/local/bin/sops /usr/bin/sops

LABEL containers.bootc=1
ENV container=oci
STOPSIGNAL SIGRTMIN+3
CMD ["/sbin/init"]
SHELL ["/bin/bash", "-xeuo", "pipefail", "-c"]

RUN dnf -y install \
	bind-utils bluez btop cockpit cockpit-podman fd-find git htop ncurses \
	neovim python3 restic ripgrep rsync tcpdump which wireguard-tools wireshark-cli zsh \
	arm-image-installer bcm283x-firmware uboot-images-armv8 brcmfmac-firmware \
	NetworkManager-wifi firewalld chrony \
	&& dnf clean all \
	&& rm -rf /var/cache/* /var/log/* /run/dnf /tmp/* /var/tmp/*

COPY --chmod=0644 users/jh.pub /usr/share/homelab/ssh/jh.keys

COPY quadlets/ /usr/share/containers/systemd/
COPY configs/environment/ /usr/share/homelab/environment/
COPY configs/defaults/ /usr/share/homelab/defaults/
COPY secrets/*.enc.env /usr/share/homelab/secrets/
COPY --chmod=0755 scripts/homelab /usr/libexec/homelab
COPY systemd/ /usr/lib/systemd/system/

# Keep heredocs inside Bash; Ubuntu's packaged builder does not parse them.
COPY scripts/build-host /usr/libexec/homelab-build-host
RUN ["/bin/bash", "/usr/libexec/homelab-build-host"]

RUN bootc container lint
