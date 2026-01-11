![Header Image](https://raw.githubusercontent.com/Mafyuh/homelab-svg-assets/main/assets/header_.png)

<div align="center">

# homelab (wip)

| Hardware | OS | Tools | Secrets |
|---|---|---|---|
[![Raspberry Pi Badge](https://img.shields.io/badge/Raspberry%20Pi-black?logo=raspberrypi&logoColor=fff&style=for-the-badge)](https://www.raspberrypi.com/products/raspberry-pi-4-model-b/) | [![Fedora](https://img.shields.io/badge/Fedora-black?style=for-the-badge&logo=fedora&logoColor=white)](https://fedoraproject.org/de/iot/) | [![Podman](https://img.shields.io/badge/Podman-black?logo=podman&logoColor=fff&style=for-the-badge)](https://podman.io/) [![Ansible](https://img.shields.io/badge/-Ansible-black?logo=ansible&logoColor=red&style=for-the-badge)](https://www.ansible.com/) | [![SOPS](https://img.shields.io/badge/-SOPS-black?logoColor=fff&style=for-the-badge)](https://github.com/getsops/sops) [![age](https://img.shields.io/badge/-age-black?logoColor=fff&style=for-the-badge)](https://github.com/FiloSottile/age)

</div>

# 📖 Overview

This repo contains the source of my personal homelab that runs a Raspberry Pi 4 Model B 8GB locally on my network.

Secrets are encrypted using [sops](https://github.com/getsops/sops) and a [age](https://github.com/FiloSottile/age) asymmetric key pair.

## 🗃️ Folder Structure
```shell
├── 📁 .github                      # CI/CD workflows and actions
├── 📁 ansible                      # Application deployments
│   ├── 📁 inventory
│   ├── 📁 roles
│   └──    ansible.cfg
├── 📁 configs                      # Configuration files for containers
│   ├── 📁 adguard
│   ├── 📁 caddy
│   └── 📁 other apps
├── 📁 quadlets                     # Systemd unit file templates for pods and containers
├── 📁 scripts                      # Builds and helper scripts
├── 📁 secrets                      # SOPS-encrypted secrets
├── 📁 users                        # Public ssh keys for users
├── .sops.yaml                      # SOPS configuration
└── README.md
```

# 🧑‍💻 Setup

The first thing to do is to use the private key of the root.pub public ssh key to generate a installable fedora iot image.

Then use the ansible `bootstrap` playbook to setup some bare minimums, like users and permissions.

## containers

`systemd` unit files are used to define podman pods and containers. This allows them to really nicely integrate into the linux system (like starting on boot, restart on failure, dependency resolution, etc.).

Use the `configure` and `containers` playbooks to setup necessary system components like the firewall and the container unit files.

*Notice: The `containers` playbook requires `BW_SESSION` being set in the environment before running `ansible-playbook`. See the secrets role for more info.*

## Users

- `root.pub`: Used when installing linux
- `admin.pub`: The jh user that has sudo permissions without password
- `picasso.pub`: The unprivileged user that runs userland podman containers

Initially, all containers used UserNS with `keep-id` to map the user namespace of `picasso` into the container. This allows `picasso` to read and edit any file that is stored inside the container in a shared volume directory.
The inherent disadvantage is that containers can potentially attack each other now, as they run in the same user namespace.

A more secure alternative is to use `auto` on ALL containers, so that the host user is not mapped inside the container and each container uses a isolated user namespace.
See also https://github.com/containers/podman/issues/20845.

Additionally, newer linux kernels support `idmapped` mounts, which allow the system to remap the ownership of files on the fly for a specific mount point, without actually changing the file ownership on the physical disk.

## 🔒 Secrets

Secrets are encrypted using sops and an age key that is stored securely, e.g. in bitwarden, as a secure note.

How to edit secrets (using bitwarden):
1. Unlock the vault by reading the master password from stdin or a file and then setting the `BW_SESSION` environment variable:
```bash
    export BW_SESSION=$(bw unlock --raw)
```

2. Instruct SOPS to retrieve the age private key by executing the following command and taking its output:
```bash
    export SOPS_AGE_KEY_CMD="zsh -c \"bw list items --search 'homelab secrets age de-/encryption key' | jq -r '.[0].fields[] | select(.name == \\\"private key\\\") | .value'\""
```

3. Edit the secrets file using sops:
```bash
    sops edit files/secrets/.env.adguard
```

## Backup

TODO!

## Helpful commands

- `systemd-analyze --user --generators=true verify X.service` - Check for errors during systemd unit generation
- `journalctl`
    - `-r` - Show all messages in the journal sorted by recently.
    - `-f` - Follow logs as they are coming in.
    - `-u` - Select a service unit to filter for.
    - `-n X` - Show the last X lines of the journal.
