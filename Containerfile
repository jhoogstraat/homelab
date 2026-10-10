# Rebuild the verified SOPS release with dependency security fixes.
FROM docker.io/library/golang:1.27.2-alpine@sha256:c2b8d9b05d9386fe1b01bab829eda3a05edb526c220e638d3c7a73671a290672 AS sops
WORKDIR /src
RUN apk add --no-cache git \
    && git clone --depth 1 --branch v3.13.3 https://github.com/getsops/sops.git . \
    && test "$(git rev-parse HEAD)" = 26e2f4784ca61353082c32dbd987c25eda086dc9 \
    && go get golang.org/x/crypto@v0.57.0 golang.org/x/net@v0.60.0 google.golang.org/grpc@v1.83.2 \
    && CGO_ENABLED=0 go build -trimpath -ldflags='-s -w' -o /usr/local/bin/sops ./cmd/sops
FROM quay.io/fedora/fedora-bootc:45
COPY --from=sops /usr/local/bin/sops /usr/bin/sops

LABEL containers.bootc=1
ENV container=oci
STOPSIGNAL SIGRTMIN+3
CMD ["/sbin/init"]
SHELL ["/bin/bash", "-xeuo", "pipefail", "-c"]

RUN dnf -y upgrade --refresh \
	&& dnf -y install \
	bind-utils bluez btop cockpit cockpit-podman fd-find git htop ncurses \
	neovim python3 restic ripgrep rsync tcpdump which wireshark-cli zsh \
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
