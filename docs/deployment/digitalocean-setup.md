# DigitalOcean Droplet Setup Guide

This guide walks through setting up a DigitalOcean droplet for running Erebus in production.

## Recommended Droplet

**Plan**: Basic Droplet - `s-2vcpu-4gb`
- **Cost**: $24/month
- **vCPU**: 2
- **RAM**: 4GB
- **SSD**: 80GB
- **Transfer**: 4TB

**Region**: Choose the closest to your location for lowest latency.

## 1. Create the Droplet

1. Log into [DigitalOcean](https://cloud.digitalocean.com/)
2. Create > Droplets
3. Choose:
   - **Image**: Ubuntu 24.04 LTS
   - **Plan**: Basic > Regular > $24/mo (2 vCPU, 4GB RAM)
   - **Region**: Closest to you
   - **Authentication**: SSH keys (add your public key)
   - **Hostname**: `erebus` (or your preference)
4. Create Droplet

Note your droplet's IP address.

## 2. Initial Server Setup

SSH into your new droplet:

```bash
ssh root@YOUR_DROPLET_IP
```

### Install Docker

```bash
# Install Docker (this also creates the 'docker' group)
curl -fsSL https://get.docker.com | sh

# Start and enable Docker
systemctl start docker
systemctl enable docker

# Verify installation
docker --version
docker compose version
```

### Create deploy user

```bash
# Create non-root user for deployments
# You'll be prompted to set a password - use a strong one for sudo access
adduser deploy
usermod -aG sudo deploy
usermod -aG docker deploy  # docker group exists after Docker install

# Copy SSH keys to new user
mkdir -p /home/deploy/.ssh
cp ~/.ssh/authorized_keys /home/deploy/.ssh/
chown -R deploy:deploy /home/deploy/.ssh
chmod 700 /home/deploy/.ssh
chmod 600 /home/deploy/.ssh/authorized_keys
```

> **Note**: The password is only used for `sudo` commands. SSH login uses key authentication only. The deploy user is in the `docker` group, so Docker commands don't require sudo.

### Configure firewall

```bash
# Allow SSH
ufw allow OpenSSH

# Enable firewall
ufw enable

# Verify
ufw status
```

### Security hardening

```bash
# Install fail2ban
apt update && apt install -y fail2ban

# Enable automatic security updates
apt install -y unattended-upgrades
dpkg-reconfigure -plow unattended-upgrades
```

## 3. Deploy Erebus

### Clone repository

```bash
# Create application directory
mkdir -p /opt/erebus
chown deploy:deploy /opt/erebus

# Switch to deploy user
su - deploy

# Clone the repository
cd /opt
git clone https://github.com/kylestratis/erebus.git
cd erebus
```

### Configure environment

```bash
# Copy example env
cp .env.example .env

# Edit with your credentials
nano .env
```

> **Tip**: If you already have a working `.env` file locally, you can sync it to the server instead:
> ```bash
> # From your local machine (after adding DEPLOY_HOST and DEPLOY_USER to .env)
> mise run deploy:env
> ```

Required variables:
```bash
DISCORD_BOT_TOKEN=your_discord_bot_token
DISCORD_USER_ID=your_discord_user_id
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
TODOIST_API_KEY=your_todoist_token
POSTGRES_PASSWORD=a_secure_random_password
ENVIRONMENT=production
LOG_LEVEL=INFO
```

### Build the Docker image (first time only)

Before the first deploy, you need to build and push the image to GHCR:

1. Go to your GitHub repo → **Actions** tab
2. Select the **Deploy** workflow
3. Click **Run workflow** → **Run workflow**

This builds the image and pushes it to `ghcr.io/kylestratis/erebus:latest`. The deploy step will fail (server not ready yet), but the image will be available.

### Log in to GitHub Container Registry

Create a classic Personal Access Token at https://github.com/settings/tokens/new:
- **Note**: `erebus-deploy` (or similar)
- **Scopes**: Select `read:packages`

Then log in on the droplet:

```bash
echo "YOUR_GITHUB_TOKEN" | docker login ghcr.io -u YOUR_GITHUB_USERNAME --password-stdin
```

### Start services

```bash
cd /opt/erebus

# Pull images
docker compose -f docker-compose.prod.yml pull

# Start all services
docker compose -f docker-compose.prod.yml up -d

# Check status
docker compose -f docker-compose.prod.yml ps

# View logs
docker compose -f docker-compose.prod.yml logs -f
```

## 4. Create GitHub Environment

1. Go to **Settings > Environments**
2. Create environment: `production`
3. (Optional) Add protection rules:
   - Required reviewers
   - Wait timer

## 5. Configure GitHub Actions Secrets

Add these as **environment secrets** under the `production` environment:

1. Go to **Settings > Environments > production**
2. Under **Environment secrets**, click **Add secret** for each:

| Secret | Description |
|--------|-------------|
| `DROPLET_HOST` | Your droplet's IP address |
| `DROPLET_USER` | `deploy` |
| `DROPLET_SSH_KEY` | Private SSH key (generate a new one for CI) |

> **Why environment secrets?** They're only exposed to jobs that explicitly declare `environment: production`, providing better security than repository-wide secrets.

### Generate CI SSH key

```bash
# On your local machine
ssh-keygen -t ed25519 -C "github-actions-erebus" -f ~/.ssh/erebus-deploy

# Copy PUBLIC key to droplet
ssh-copy-id -i ~/.ssh/erebus-deploy.pub deploy@YOUR_DROPLET_IP

# Add PRIVATE key content to GitHub secret DROPLET_SSH_KEY
cat ~/.ssh/erebus-deploy
```

## 6. Set Up Systemd Service (Optional)

For auto-restart on boot:

```bash
sudo nano /etc/systemd/system/erebus.service
```

```ini
[Unit]
Description=Erebus Discord Bot
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
User=deploy
Group=deploy
WorkingDirectory=/opt/erebus
ExecStart=/usr/bin/docker compose -f docker-compose.prod.yml up -d
ExecStop=/usr/bin/docker compose -f docker-compose.prod.yml down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
```

Enable the service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable erebus
sudo systemctl start erebus
```

## Verification

After deployment:

```bash
# Check all containers are running
docker compose -f docker-compose.prod.yml ps

# Check Erebus logs
docker logs erebus -f

# Check Letta health (port not exposed to host, use docker exec)
docker exec erebus-letta curl -sL http://localhost:8283/health
```

Test by sending a DM to your Discord bot.

## Maintenance

### View logs

```bash
# All containers
docker compose -f docker-compose.prod.yml logs -f

# Just Erebus
docker logs erebus -f --tail=100

# Just Letta
docker logs erebus-letta -f --tail=100
```

### Restart services

```bash
docker compose -f docker-compose.prod.yml restart
```

### Update manually

```bash
cd /opt/erebus
git pull
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d
```

### Database backup

```bash
# Backup PostgreSQL
docker exec erebus-postgres pg_dump -U letta letta > backup-$(date +%Y%m%d).sql

# Restore (if needed)
cat backup.sql | docker exec -i erebus-postgres psql -U letta letta
```

## Troubleshooting

### Container won't start

```bash
# Check logs
docker logs erebus

# Check if port is in use
netstat -tlnp | grep 8283
```

### Out of memory

```bash
# Check memory usage
docker stats

# If Letta is using too much, restart it
docker restart erebus-letta
```

### Disk space

```bash
# Check disk usage
df -h

# Clean up Docker
docker system prune -af
```
