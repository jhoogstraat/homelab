# Homelab

This repo contains the source of my personal homelab that runs a raspberry pi 4 8GB locally on my network.

It does not contain any unencrypted passwords or secrets, because that would be dumb. Don't even try.

Directory structure:

- config/: contains config files for the containers.
- containers/: Contains the systemd unit files for pods and containers.
- custom-images/: Dockerfiles to build custom images that can't be fetched remotely.
- playbooks/: A location for all playbooks.
- storage/: Contains empty or prefilled storage directories for the containers.
- secrets/: SOPS-encrypted secrets using the admin private ssh key
- users/: A list of public ssh keys that are imported to the target server.

TODO: As the storage dirs are actively used and modified we cannot just push the static static from the repo...

## Setup

The first thing to do is to use the private key of the root.pub public ssh key to generate a installable fedora iot image.

Then use the ansible `ìnit` playbook to setup some bare minimums, like users and permissions.

## Setup containers

`systemd` unit files are used to define podman pods and containers. This allows them to really nicely integrate into the linux system (like starting on boot, restart on failure, dependency resolution, etc.).

Use the `infra` and `container` playbooks to setup necessary system components like the firewall and the container unit files.

## Users

- root.pub: Used when installing linux
- admin.pub: The jh user that has sudo permissions without password
- picasso.pub: The unprivliged user that runs userland podman containers

## Secrets

Secrets are encrypted using sops and a age key that is stored in vaultwarden as a secure note (item-id 5cbdfdb6-f629-454a-a37f-bf763a721586).

- encrypt: Use `encrypt_all.sh` to encrypt all .env files under /secrets with the public key that corresponds to the private key in vaultwarden.
- decrypt: Copy the private age key from the secret note in vaultwarden and use it as the variable SOPS_AGE_KEY together with the script `decrypt_all.sh`.

To sync all secrets to the homelab server use the ansible playbook `secrets.playbook.yaml`. This action requires the bitwarden cli (`bw`) to be installed and logged in to the account with the age private key note.
It will then asks for the master password to unlock the vault and fetch the secret note value (the age private key) to unlock and sync all .env files to the homelab server.

Caution: For this playbook to work all secrets must be in encrypted state.

## Backup

TODO!
