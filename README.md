![Header Image](https://raw.githubusercontent.com/Mafyuh/homelab-svg-assets/main/assets/header_.png)

<div align="center">

# homelab (wip)

| Hardware | OS | Tools | Secrets |
|---|---|---|---|
[![Raspberry Pi Badge](https://img.shields.io/badge/Raspberry%20Pi-black?logo=raspberrypi&logoColor=fff&style=for-the-badge)](https://www.raspberrypi.com/products/raspberry-pi-4-model-b/) | [![Fedora](https://img.shields.io/badge/Fedora-black?style=for-the-badge&logo=fedora&logoColor=white)](https://fedoraproject.org/de/iot/) | [![Podman](https://img.shields.io/badge/Podman-black?logo=podman&logoColor=fff&style=for-the-badge)](https://podman.io/) [![Ansible](https://img.shields.io/badge/-Ansible-black?logo=ansible&logoColor=red&style=for-the-badge)](https://www.ansible.com/) | [![SOPS](https://img.shields.io/badge/-SOPS-black?logoColor=fff&style=for-the-badge)](https://github.com/getsops/sops) [![age](https://img.shields.io/badge/-age-black?logoColor=fff&style=for-the-badge)](https://github.com/FiloSottile/age)

</div>

# 📖 Overview

- This repo contains the source of my personal homelab that runs a Raspberry Pi 4 Model B 8GB locally on my network.

- Containers run using [podman](https://podman.io/) and [systemd](https://systemd.io/) as Quadlets and are deployed using [ansible](https://www.ansible.com/).

- Secrets are encrypted using [sops](https://github.com/getsops/sops) and a [age](https://github.com/FiloSottile/age) asymmetric key pair.

- TLS termination and reverse proxying is done using [traefik](https://traefik.io/).


# 🧑‍💻 Setup

1. Use the private key of the root.pub public ssh key to generate a installable fedora iot image.
2. Then use the ansible `bootstrap` playbook to setup some bare minimums, like users and permissions.
3. Use the `configure` playbook to setup system components like the firewall.
4. Configure your specific cert provider inside `traefik.yml`.
5. Finally use the `containers` playbook to deploy all containers.

# Technical details

## 🗃️ Folder Structure
```shell
├── 📁 .github                      # CI/CD workflows and actions
├── 📁 ansible                      # Application deployments
│   ├── 📁 inventory
│   ├── 📁 roles
│   └──    ansible.cfg
├── 📁 configs                      # Configuration files for containers
│   ├── 📁 adguard
│   ├── 📁 traefik
│   └── 📁 other apps
├── 📁 quadlets                     # Systemd unit file templates for pods and containers
├── 📁 scripts                      # Builds and helper scripts
├── 📁 secrets                      # SOPS-encrypted secrets
├── 📁 users                        # Public ssh keys for users
├── .sops.yaml                      # SOPS configuration
└── README.md
```

## Containers

`systemd` unit files are used to define podman pods and containers. This allows them to really nicely integrate into the linux system (like starting on boot, restart on failure, dependency resolution, etc.).
It is like a integrated kubernetes-lite.

All containers use `userns=auto` to run processes in a random user namespace.
This prevents container processes to be able to attack each other, as they all run in different user namespaces.
See also https://github.com/containers/podman/issues/20845.

Additionally, newer linux kernels support `idmapped` mounts, which allow the system to remap the ownership of files on the fly for a specific mount point, without actually changing the file ownership on the physical disk.
This is used to map config and data files into containers with the correct ownership. Special attention is given to containers that do not run the root user inside. Here the mapping has to be matched to the target uid:gid inside the container.

## Deployment

Ansible is used to deploy and manage the homelab.

The `bootstrap` playbook is used to setup bare minimums on a fresh fedora iot installation, like creating the admin user and setting up ssh access.

The `configure` playbook sets up basic port forwarding (mainly 443 and 53).

The `containers` playbook deploys all containers defined in the `quadlets` folder + their respective configuration files from the `configs` folder + any necessary secrets from the `secrets` folder.
Secrets are first decrypted using the age private key before being copied to the server. This means that you have to enter your age private key each time when running the playbook.
The playbooks is not (yet) idempotent, but already tries to only restart containers if something changed. If anything goes wrong you can always restart services manually using `systemtl restart <service>`.

## Routing

Each service is exposed under its own subdomain, e.g. `adguard.example.com`.

Traefik is configured via `traefik.yml`. Basic rules for tls, entrypoints and the docker provider life there.
Inside of the container quadlets you only have to define `traefik.enable=true` for traefik to pick up the service and route it correctly. Otherwise it will be skipped.
Using the `defaultRule` option from traefik, the subdomain is either defined by the container name or an explicit custom `subdomain=xyz` label (see vaultwarden quadlet for an example).

### TLS
Traefik automatically provisions and renews TLS certificates using Let's Encrypt.
It uses a DNS challenge to issue a wildcard certificate (`*.example.com`) that all services then use.

*This must be adapted to your specific environment. Define your DNS provider and environment args required inside `traefik.yml`*.

## Users

- `root.pub`: Used when installing linux
- `jh.pub`: The jh user that has sudo permissions without password

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
