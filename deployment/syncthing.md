# Syncthing Setup for Obsidian Vault

This guide covers setting up Syncthing to sync your Obsidian vault between your local machine and the DigitalOcean droplet.

## Overview

Syncthing provides encrypted peer-to-peer sync between devices. For Erebus:
- **Your Mac**: Source of truth, where you edit notes in Obsidian
- **Droplet**: Replica for Erebus to read/write notes
- **Sync**: Bidirectional, near real-time when both devices are online

## Prerequisites

- DigitalOcean droplet with Erebus deployed (see [digitalocean-setup.md](digitalocean-setup.md))
- Obsidian vault on your local machine

## 1. Install Syncthing on the Droplet

SSH into your droplet as root:

```bash
ssh root@YOUR_DROPLET_IP
```

Add the Syncthing repository and install:

```bash
# Add Syncthing release key
curl -o /usr/share/keyrings/syncthing-archive-keyring.gpg https://syncthing.net/release-key.gpg

# Add repository
echo "deb [signed-by=/usr/share/keyrings/syncthing-archive-keyring.gpg] https://apt.syncthing.net/ syncthing stable" | tee /etc/apt/sources.list.d/syncthing.list

# Install
apt update && apt install -y syncthing
```

Create the vault directory:

```bash
mkdir -p /opt/vault
chown deploy:deploy /opt/vault
```

Enable Syncthing as a service for the deploy user:

```bash
systemctl enable syncthing@deploy
systemctl start syncthing@deploy
```

Get the device ID (save this for pairing):

```bash
su - deploy -c "syncthing --device-id"
```

## 2. Access the Droplet's Syncthing Web UI

Syncthing's web UI only listens on localhost by default. Use an SSH tunnel to access it:

```bash
# From your local machine
ssh -L 8384:localhost:8384 deploy@YOUR_DROPLET_IP
```

Then open http://localhost:8384 in your browser.

> **First-time setup**: You'll be prompted to set a username/password. Do this to secure the UI.

## 3. Install Syncthing on Your Mac

```bash
brew install syncthing
brew services start syncthing
```

Open http://localhost:8384 in your browser (this is your Mac's Syncthing UI, different from the droplet's).

## 4. Pair the Devices

### On the droplet's web UI (via SSH tunnel):

1. Go to **Actions > Show ID**
2. Copy the Device ID

### On your Mac's Syncthing UI:

1. Click **Add Remote Device**
2. Paste the droplet's Device ID
3. Set **Device Name** to `erebus-droplet`
4. Click **Save**

### On the droplet's web UI:

1. A notification will appear asking to add your Mac
2. Click **Add Device**
3. Set a name like `macbook`
4. Click **Save**

Both devices should now show as "Connected".

## 5. Share Your Vault Folder

### On your Mac's Syncthing UI:

1. Click **Add Folder**
2. Configure:
   - **Folder Label**: `Obsidian Vault` (display name)
   - **Folder ID**: `obsidian-vault` (must match on both devices)
   - **Folder Path**: `/Users/YOU/Obsidian/your-vault-name`
3. Under **Sharing**, check the box for `erebus-droplet`
4. Click **Save**

### On the droplet's web UI:

1. A notification will appear to accept the shared folder
2. Click **Add**
3. Set **Folder Path** to `/opt/vault`
4. Click **Save**

The initial sync will begin. For large vaults, this may take a few minutes.

## 6. Verify Sync

On the droplet:

```bash
ls -la /opt/vault
```

You should see your vault contents.

## 7. Configure Erebus

Ensure your `.env` on the droplet has:

```bash
OBSIDIAN_VAULT_PATH=/opt/vault
```

The docker-compose.prod.yml already mounts this path:

```yaml
volumes:
  - ${OBSIDIAN_VAULT_PATH:-/opt/vault}:/vault:ro
```

Restart Erebus to pick up the vault:

```bash
docker compose -f docker-compose.prod.yml restart erebus
```

## 8. Secure the Web UI (Optional but Recommended)

After initial setup, you can restrict or disable the web UI.

```bash
# On the droplet (path may vary by Syncthing version)
nano /home/deploy/.local/state/syncthing/config.xml
# Or older versions: /home/deploy/.config/syncthing/config.xml
```

**Option A: Restrict to localhost only** (recommended - still accessible via SSH tunnel)

```xml
<gui enabled="true" tls="false" debugging="false">
    <address>127.0.0.1:8384</address>
    ...
</gui>
```

**Option B: Fully disable the web UI**

```xml
<gui enabled="false" tls="false" debugging="false">
    ...
</gui>
```

Restart Syncthing to apply:

```bash
systemctl restart syncthing@deploy
```

## Troubleshooting

### Devices not connecting

Check if Syncthing port is blocked:

```bash
# On droplet
ufw allow 22000/tcp   # Syncthing data
ufw allow 21027/udp   # Syncthing discovery
```

### Sync conflicts

Syncthing creates `.sync-conflict-*` files when the same file is modified on both devices simultaneously. Erebus primarily creates new files, so conflicts should be rare.

To find conflicts:

```bash
find /opt/vault -name "*.sync-conflict-*"
```

### Check sync status

```bash
# View Syncthing logs
journalctl -u syncthing@deploy -f

# Check folder status via API
curl -s http://localhost:8384/rest/db/status?folder=obsidian-vault | jq
```

### Vault not accessible in container

Verify the volume mount:

```bash
docker exec erebus ls -la /vault
```

If empty, check that `OBSIDIAN_VAULT_PATH` is set correctly in `.env`.

## Maintenance

### View sync status

Access via SSH tunnel:

```bash
ssh -L 8384:localhost:8384 deploy@YOUR_DROPLET_IP
# Then open http://localhost:8384
```

### Update Syncthing

```bash
apt update && apt upgrade syncthing
systemctl restart syncthing@deploy
```

### Backup consideration

Syncthing is not a backup. Your vault should have independent backups (Obsidian Sync, Time Machine, etc.). Syncthing provides real-time replication, not point-in-time recovery.
