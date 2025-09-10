# Homelab

This repo contains the source of my personal homelab that runs a raspberry pi 4 8GB locally on my network.

It does not contain any unencrypted passwords or secrets, because that would be dumb. Don't even try.

Directory structure:

- `files/`: All files that are used or synced to the host by ansible.
    - `build/`: Dockerfiles to build custom images that can't be fetched remotely.
    - `configs/`: Config files for the containers.
    - `data/`: Empty or prefilled storage directories for the containers.
    - `secrets/`: SOPS-encrypted secrets using a age key.
    - `quadlets/`: Systemd unit file templates for pods and containers.
    - `users/`: A list of public ssh keys that are imported to the target server.
- `inventory/`: Ansible inventory that defines some basic vars and the raspberry target.
- `roles/`: Custom ansible roles that are used by the playbooks


TODO: As the storage dirs are actively used and modified we cannot just push the static static from the repo...

## Setup

The first thing to do is to use the private key of the root.pub public ssh key to generate a installable fedora iot image.

Then use the ansible `bootstrap` playbook to setup some bare minimums, like users and permissions.

## Setup containers

`systemd` unit files are used to define podman pods and containers. This allows them to really nicely integrate into the linux system (like starting on boot, restart on failure, dependency resolution, etc.).

Use the `configure` and `containers` playbooks to setup necessary system components like the firewall and the container unit files.

*Notice: The `containers` playbook requires `BW_SESSION` being set in the environment before running `ansible-playbook`. See the secrets role for more info.*

## Users

- root.pub: Used when installing linux
- admin.pub: The jh user that has sudo permissions without password
- picasso.pub: The unprivliged user that runs userland podman containers

## Secrets

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

- `systemd-analyze --user --generators=true verify adguard.service` - Check for errors during systemd unit generation
- `journalctl -r` - Show all messages in the journal sorted by recently.
