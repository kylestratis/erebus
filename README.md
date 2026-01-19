# Erebus

> 🌑 A stateful, continuously-learning AI assistant accessible via Discord

*"Erebus, primordial deity of shadow - the darkness through which all things pass"*

**Status**: 🚧 In Development - MVP Phase

# Overview

Erebus is a Discord-based AI assistant that operates in the liminal space between thought and action:

- **EidolonMemory**: Stateful memory system powered by Letta that learns your patterns and preferences across sessions
- **Productivity Integration**: Todoist tasks, Obsidian notes, scheduled jobs
- **Intelligent Scheduling**: Automated daily notes, end-of-day sync, weekly reviews
- **Secure Architecture**: DM-only, user whitelist, agent isolation

## Architecture

```
Discord Bot
    │
    ▼
EidolonMemory (wrapper)
    │
    ▼ REST API
Letta Server (Docker)
    ├── Agent per user
    │   ├── Core Memory (persona, user profile)
    │   ├── Archival Memory (learned patterns)
    │   └── Recall Memory (conversation history)
    │
    └── Tools (client-side execution)
        ├── Vault tools (Obsidian operations)
        ├── MCP tools (Todoist via MCP server)
        └── System tools (introspection)
    │
    ▼
PostgreSQL (state persistence)
```

## Project Structure

```
erebus/
├── config/           # Unified configuration system
│   └── __init__.py   # ErebusConfig, MCPServerConfig, etc.
├── bot/              # Discord bot
│   ├── cogs/         # Command modules (slash commands)
│   ├── scheduler/    # Automated jobs (daily note, sync, weekly review)
│   └── client.py     # Discord client with auth
├── agents/           # AI agent integrations
│   ├── eidolon/      # EidolonMemory (Letta wrapper)
│   ├── mcp/          # MCP client for tool servers
│   ├── models/       # LLM providers (Anthropic)
│   └── vault/        # Obsidian vault operations
├── docker/           # Docker configurations
│   └── letta/        # Letta server + PostgreSQL
├── docs/             # Documentation
├── .env              # All configuration (copy from .env.example)
├── config.toml       # MCP servers only (optional, copy from config.example.toml)
└── tests/            # Test suite
```

## Local Development

### Prerequisites

- Python 3.11+
- [mise](https://mise.jdx.dev/) for tool management
- [uv](https://github.com/astral-sh/uv) for Python dependency management
- Docker and Docker Compose
- Git

### Quick Start

```bash
# Clone repository
git clone https://github.com/kylestratis/erebus.git
cd erebus

# Install dependencies (mise + uv)
mise install
uv sync

# Copy environment template and add your credentials
cp .env.example .env
# Edit .env with your Discord token, user ID, and API keys
```

### Start Letta Server

Letta provides the stateful memory backend. Start it with Docker:

```bash
cd docker/letta
docker compose up -d
```

This starts:
- **Letta server** on `http://localhost:8283`
- **PostgreSQL** for persistent storage

Verify it's running:
```bash
curl http://localhost:8283/health
```

### Configure Environment

Edit `.env` with your credentials:

```bash
# Required
DISCORD_BOT_TOKEN=your_discord_bot_token
DISCORD_USER_ID=your_discord_user_id

# For AI features
ANTHROPIC_API_KEY=sk-ant-...  # Used by Letta for Claude
OPENAI_API_KEY=sk-...         # Used by Letta for embeddings

# Letta connection (default is localhost)
LETTA_API_URL=http://localhost:8283

# Optional integrations
TODOIST_API_TOKEN=your_todoist_token
OBSIDIAN_VAULT_PATH=/path/to/your/vault
```

### Run the Bot

```bash
# Run tests first
uv run pytest

# Start the bot
uv run python -m bot

# Start with debug logging
uv run python -m bot --debug
```

### Stopping Services

```bash
# Stop the bot with Ctrl+C

# Stop Letta server
cd docker/letta
docker compose down

# To also remove data volume
docker compose down -v
```

## DigitalOcean Deployment

### Recommended Droplet

**Plan**: Basic `s-2vcpu-4gb` at **$24/month**
- 2 vCPU, 4GB RAM, 80GB SSD, 4TB transfer
- Sufficient for Erebus + Letta + PostgreSQL

See [docs/deployment/digitalocean-setup.md](docs/deployment/digitalocean-setup.md) for the complete setup guide.

### Quick Start

```bash
# On your droplet
git clone https://github.com/kylestratis/erebus.git /opt/erebus
cd /opt/erebus
cp .env.example .env
nano .env  # Add your credentials

# Start all services
docker compose -f docker-compose.prod.yml up -d
```

### Automatic Deployment

Push to `main` triggers automatic deployment via GitHub Actions:
1. Builds Docker image and pushes to GitHub Container Registry
2. SSHs into droplet and restarts the erebus container
3. Watchtower also polls for updates every 5 minutes

Required GitHub Secrets:
- `DROPLET_HOST` - Your droplet IP
- `DROPLET_USER` - SSH user (e.g., `deploy`)
- `DROPLET_SSH_KEY` - Private SSH key for deployment

### Local Deployment Tasks

Use mise for deployment operations:

```bash
# Add to your .env
DEPLOY_HOST=your-droplet-ip
DEPLOY_USER=deploy

# Sync environment changes
mise run deploy:env

# View logs
mise run deploy:logs

# SSH into server
mise run deploy:ssh

# Check status
mise run deploy:status
```

### Vault Sync with Syncthing

To sync your Obsidian vault to the droplet:

1. Install Syncthing on the droplet
2. Configure folder sync from your local vault
3. Set `OBSIDIAN_VAULT_PATH` to the synced location

## Configuration Reference

Erebus uses [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) for configuration management with automatic validation.

### Configuration Files

| File | Purpose | Git-tracked |
|------|---------|-------------|
| `.env.example` | Template for all settings | Yes |
| `.env` | Your configuration | No |
| `config.example.toml` | MCP server configuration template | Yes |
| `config.toml` | Your MCP server configuration | No |

### Command Line Options

| Option | Description |
|--------|-------------|
| `--debug` | Enable debug logging (overrides LOG_LEVEL) |
| `--log-level LEVEL` | Set log level (DEBUG, INFO, WARNING, ERROR, CRITICAL) |

### Environment Variables

All configuration is done via environment variables in `.env`:

#### Required

| Variable | Description |
|----------|-------------|
| `DISCORD_BOT_TOKEN` | Discord bot token from the Developer Portal |
| `DISCORD_USER_ID` | Your Discord user ID (numeric) |
| `ANTHROPIC_API_KEY` | Anthropic API key (used by Letta for Claude) |
| `OPENAI_API_KEY` | OpenAI API key (used by Letta for embeddings) |

#### Recommended

| Variable | Description |
|----------|-------------|
| `TODOIST_API_TOKEN` | Todoist API token for task management |

#### Optional

| Variable | Default | Description |
|----------|---------|-------------|
| `DISCORD_GUILD_ID` | - | Guild ID for faster command sync during development |
| `ALLOWED_USER_IDS` | `DISCORD_USER_ID` | Comma-separated list of allowed user IDs |
| `OBSIDIAN_VAULT_PATH` | - | Path to Obsidian vault root |
| `OBSIDIAN_TEMPLATES_PATH` | `Templates` | Relative path to templates directory |
| `OBSIDIAN_DAILY_NOTES_PATH` | `Calendar/Daily Notes` | Relative path to daily notes |
| `OBSIDIAN_DAILY_NOTE_FORMAT` | `%Y-%m-%d` | strftime format for daily note filenames |
| `LETTA_API_URL` | `http://localhost:8283` | Letta server API URL |
| `LETTA_API_KEY` | - | Letta API key (if using remote server) |
| `ENVIRONMENT` | `development` | `development`, `staging`, or `production` |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `SCHEDULER_ENABLED` | `true` | Enable/disable all scheduled jobs |
| `SCHEDULER_TIMEZONE` | `America/New_York` | IANA timezone for job schedules |

See `.env.example` for a complete template with all available options.

### MCP Server Configuration (config.toml)

MCP servers are configured in `config.toml` (for array syntax support):

```toml
# Todoist is auto-configured from TODOIST_API_TOKEN in .env
# Only add entries here for custom MCP servers

[[mcp.servers]]
name = "github"
command = "npx"
args = ["@modelcontextprotocol/server-github"]
[mcp.servers.env]
GITHUB_TOKEN = "your-github-token"
```

See `config.example.toml` for more examples.

## Features

### MVP (Current Phase)
- [x] Project scaffolding (mise, uv, Docker, pre-commit)
- [x] Discord bot with user authentication (whitelist + DM-only)
- [x] Natural conversation with Claude (via Letta)
- [x] Todoist integration (via MCP)
- [x] Obsidian vault integration (direct file I/O)
- [x] Slash commands (`/daily`, `/idea`, `/capture`, `/sync`, `/weekly`, `/journal`)
- [x] EidolonMemory system (Letta) with persistent memory
- [x] Scheduled jobs (daily note with morning briefing, end-of-day sync, weekly review)

### Phase 2 (Planned)
- [ ] Sanitizer agent for untrusted content
- [ ] Task prioritization engine
- [ ] GitHub integration
- [ ] Anki card generation
- [ ] Readwise highlight resurfacing
- [ ] Autonomous background tasks

### Phase 3 (Future)
- [ ] Calendar integration
- [ ] Multi-model support (OpenAI, local models)
- [ ] Email integration
- [ ] Advanced scheduling optimization

## Documentation

- [Implementation Checklist](https://github.com/kylestratis/erebus/wiki/Implementation)
- [EidolonMemory Architecture](docs/eidolon-memory.md)
- [MCP Server Documentation](docs/mcp/) (TODO)
- [Deployment Guide](docs/deployment/) (TODO)

## Security

- **Agent Isolation**: Separate agents for trusted vs untrusted content
- **User Whitelist**: Only responds to authorized Discord user ID
- **Token Auth**: All MCP servers require authentication
- **No Auto-Commits**: All destructive operations require user approval

See [Security Architecture](docs/security.md) (TODO) for details.

## License

MIT License - See [LICENSE](LICENSE) file

## Name & Mythology

**Erebus** (Ἔρεβος) - Primordial Greek deity of darkness and shadow, born of Chaos. Brother to Nyx (Night), father to Aether (Light) and Hemera (Day). The personification of deep darkness, the void through which souls pass between worlds.

**EidolonMemory** (εἴδωλον) - The phantom that remembers. Greek for "image, phantom, ghost" - Plato's imperfect copies learning to reflect ideal forms. The memory system that learns and mirrors your patterns.

*"In darkness, all things are possible. In memory, all things persist."*
