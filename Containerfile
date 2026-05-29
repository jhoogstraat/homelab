FROM quay.io/fedora/fedora-bootc:45 AS builder
RUN /usr/libexec/bootc-base-imagectl build-rootfs --manifest=fedora-iot /target-rootfs

FROM scratch
COPY --from=builder /target-rootfs/ /

LABEL containers.bootc=1
ENV container=oci
STOPSIGNAL SIGRTMIN+3
CMD ["/sbin/init"]
SHELL ["/bin/bash", "-xeuo", "pipefail", "-c"]

RUN <<-'EOF'
	rpm-ostree install -y --idempotent \
		bind-utils bluez btop cockpit cockpit-podman fd-find git htop ncurses \
		neovim ripgrep rsync tcpdump which wireguard-tools wireshark-cli zsh
	ostree container commit
	rm -rf /var/cache/* /var/log/* /run/dnf /tmp/* /var/tmp/*
EOF

RUN <<-'EOF'
	cat > /usr/lib/sysusers.d/homelab-users.conf <<-'EOT'
	u jh 1000 "Joshua" /var/empty /bin/zsh
	m jh wheel
	u cockpit 4000 "Rootless unprivileged peasant with password to login to cockpit" /var/empty /bin/bash
	EOT

	systemd-sysusers /usr/lib/sysusers.d/homelab-users.conf
	usermod --lock root
	usermod --password '$6$fMTmOCP5eFVreSeb$dC/eKQPsoDu7tu0lsqAcfTvbVhNLLSBkT7ylDsPa6ucaM4Hy3msuPBnP3sTJXWlD5/ECnPYthEZPpVxt9h.pD1' cockpit
	install -d -m 0755 /usr/share/homelab/ssh
	printf '%%wheel ALL=(ALL) NOPASSWD: ALL\n' > /etc/sudoers.d/wheel-nopasswd
	chmod 0440 /etc/sudoers.d/wheel-nopasswd
	rm -rf /var/home/jh /var/home/cockpit /tmp/* /var/tmp/*
EOF

COPY --chmod=0644 users/jh.pub /usr/share/homelab/ssh/jh.keys

RUN <<-'EOF'
	install -d -m 0755 /etc/ssh/sshd_config.d
	cat > /etc/ssh/sshd_config.d/30-homelab.conf <<-'EOT'
	PasswordAuthentication no
	KbdInteractiveAuthentication no
	PermitRootLogin no
	PubkeyAuthentication yes
	Match User jh
	    AuthorizedKeysFile /usr/share/homelab/ssh/jh.keys
	EOT
EOF

RUN <<-'EOF'
	echo 'pi1.local' > /etc/hostname
	ln -snf /usr/share/zoneinfo/Europe/Berlin /etc/localtime
	install -d -m 0755 /etc/containers/registries.conf.d /etc/systemd/resolved.conf.d

	cat > /etc/containers/registries.conf.d/local_registry.conf <<-'EOT'
	[[registry]]
	location = "localhost:5000"
	insecure = true
	EOT

	cat > /etc/systemd/resolved.conf.d/custom-dns.conf <<-'EOT'
	[Resolve]
	DNS=1.1.1.1 8.8.8.8
	DNSStubListener=no
	EOT

	# https://github.com/matter-js/matterjs-server/main/docs/os_requirements.md
	cat > /etc/sysctl.d/99-matter.conf <<-'EOT'
	net.ipv6.conf.end0.forwarding=0
	net.netfilter.nf_conntrack_udp_timeout_stream=3600
	EOT
EOF

RUN <<-'EOF'
	install -d -m 0755 /opt/containers /var/opt/containers/data /var/opt/containers/secrets
	ln -sfn /var/opt/containers/data /opt/containers/data
	ln -sfn /var/opt/containers/secrets /opt/containers/secrets

	cat > /usr/lib/tmpfiles.d/homelab-containers.conf <<-'EOT'
	d /var/opt/containers 0755 root root -
	d /var/opt/containers/data 0755 root root -
	d /var/opt/containers/secrets 0700 root root -
	d /var/lib/bluetooth 0700 root root -
	d /var/lib/bluetooth/mesh 0755 root root -
	EOT
EOF

COPY quadlets/ /usr/share/containers/systemd/
COPY configs/ /opt/containers/config/

RUN <<-'EOF'
	systemctl enable bluetooth.service cockpit.socket firewalld.service podman-auto-update.timer podman.socket systemd-resolved.service
	firewall-offline-cmd --zone=public --add-service=cockpit
	firewall-offline-cmd --zone=public --add-service=https
	firewall-offline-cmd --zone=public --add-service=dns
	firewall-offline-cmd --zone=public --add-port=21063-21064/tcp
	firewall-offline-cmd --zone=public --add-port=51820/udp
	firewall-offline-cmd --zone=public --remove-port=51821/tcp || true
	rm -rf /run/cockpit /tmp/* /var/tmp/*
EOF

RUN <<-'EOF'
	printf '\n[etc]\ntransient=true\n' >> /usr/lib/ostree/prepare-root.conf
	kver=$(cd /usr/lib/modules && printf '%s\n' *)
	dracut -vf "/usr/lib/modules/$kver/initramfs.img" "$kver"
	rm -rf /var/cache/* /var/log/* /run/selinux-policy /tmp/* /var/tmp/*
EOF

RUN bootc container lint
