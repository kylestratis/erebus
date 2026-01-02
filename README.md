# Erebus

> 🌑 A stateful, continuously-learning AI assistant accessible via Discord

*"Erebus, primordial deity of shadow - the darkness through which all things pass"*

**Status**: 🚧 In Development - MVP Phase

# Overview

Erebus is a Discord-based AI assistant that operates in the liminal space between thought and action:

- **EidolonMemory**: Stateful memory system that learns your patterns and preferences (via Letta)
- **Productivity Integration**: Todoist tasks, Obsidian notes, GitHub repos
- **Intelligent Scheduling**: Task prioritization and schedule suggestions
- **Autonomous Operations**: Background research and knowledge building (2am-4am darkness window)
- **Secure Architecture**: Agent isolation to prevent "Lethal Trifecta" vulnerabilities

## Architecture

```
Discord Bot (DigitalOcean Droplet)
    ↓
├─ Erebus (Main Agent - Private data access)
│  ├─ EidolonMemory (Letta-powered stateful learning) [planned]
│  ├─ MCP Tool Access: Todoist, GitHub
│  └─ Direct Integration: Obsidian Vault (via Syncthing)
│
└─ Sanitizer Agent (Handles untrusted content) [planned]
   └─ Web scraping, file parsing
    ↓
Claude API + Anthropic SDK
    ↓
Integrations:
├─ Todoist MCP Server (@doist/todoist-ai)
├─ Obsidian Vault (direct Python file I/O, synced via Syncthing)
├─ GitHub MCP (official) [planned]
├─ Learning MCP (custom: Anki, Readwise) [planned]
└─ Calendar MCP [planned]
```

## Project Structure

```
erebus/
├── bot/              # Discord bot
│   ├── cogs/         # Command modules
│   ├── client.py     # Discord client with auth
│   ├── config.py     # pydantic-settings configuration
│   └── logging.py    # Structured logging setup
├── agents/           # AI agent integrations
│   ├── mcp/          # MCP client for tool servers
│   ├── models/       # LLM providers (Anthropic)
│   ├── vault/        # Obsidian vault operations
│   └── conversation.py
├── docs/             # Documentation
│   ├── decisions/    # Architecture decision records
│   ├── research/     # Research notes
│   └── mcp/          # MCP integration docs
├── tests/            # Test suite
└── docker/           # Docker configurations
```

## Development Setup

### Prerequisites

- Python 3.11+
- [mise](https://mise.jdx.dev/) for tool management
- [uv](https://github.com/astral-sh/uv) for Python dependency management
- Git
- Docker (for deployment)

### Quick Start

```bash
# Clone repository
git clone https://github.com/kylestratis/erebus.git
cd erebus

# Install dependencies (mise + uv)
mise install
uv sync

# Copy environment template
cp .env.example .env
# Edit .env with your credentials

# Run tests
uv run pytest

# Run bot (development)
uv run python -m bot
```

## Configuration

Erebus uses [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) for configuration management with automatic validation.

### Local Development

For local development, copy the example environment file and fill in your credentials:

```bash
cp .env.example .env
# Edit .env with your values
```

The `.env` file is automatically loaded during development. Settings are validated on startup with clear error messages for missing or invalid values.

### Docker / Production

In production (Docker), pass environment variables directly instead of using a `.env` file:

```bash
docker run -d \
  -e DISCORD_BOT_TOKEN=your_token \
  -e DISCORD_USER_ID=123456789 \
  -e CLAUDE_API_KEY=sk-ant-... \
  erebus
```

Or use Docker Compose with an environment file:

```yaml
services:
  erebus:
    image: erebus
    env_file:
      - .env.production
```

### Environment Variables

#### Required

| Variable | Description |
|----------|-------------|
| `DISCORD_BOT_TOKEN` | Discord bot token from the Developer Portal |
| `DISCORD_USER_ID` | Your Discord user ID (numeric) |

#### Recommended

| Variable | Description |
|----------|-------------|
| `CLAUDE_API_KEY` | Anthropic API key for AI features |
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
| `ENVIRONMENT` | `development` | `development`, `staging`, or `production` |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |

See `.env.example` for a complete template with all available options.

## Features

### MVP (Current Phase)
- [x] Project scaffolding (mise, uv, Docker, pre-commit)
- [x] Discord bot with user authentication (whitelist + DM-only)
- [x] Natural conversation with Claude
- [x] Todoist integration (via MCP)
- [x] Obsidian vault integration (direct file I/O)
- [ ] Slash commands (`/daily`, `/idea`)
- [ ] EidolonMemory system (Letta)
- [ ] Daily note auto-generation
- [ ] Morning briefing

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
- [EidolonMemory Architecture](docs/eidolon-memory.md) (TODO)
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
