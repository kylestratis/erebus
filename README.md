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
Discord Bot (DigitalOcean)
    ↓
├─ Erebus (Main Agent - Private data access)
│  ├─ EidolonMemory (Letta-powered stateful learning)
│  └─ MCP Tool Access: Todoist, Obsidian, Calendar, GitHub
│
└─ Sanitizer Agent (Handles untrusted content)
   └─ Web scraping, file parsing
    ↓
Claude Code SDK + Letta Memory
    ↓
MCP Servers (distributed):
├─ Todoist MCP (cloud)
├─ Obsidian MCP (custom, local/remote)
├─ GitHub MCP (official)
├─ Learning MCP (custom: Anki, Readwise)
└─ Calendar MCP (TBD)
```

## Project Structure

```
erebus/
├── bot/              # Discord bot code
├── agents/           # Erebus (main) & sanitizer agents
│   └── eidolon/      # EidolonMemory system (Letta integration)
├── mcp-servers/      # Custom MCP server implementations
│   ├── obsidian/     # Obsidian vault integration
│   └── learning/     # Anki, Readwise, reading tracker
├── config/           # Configuration files
├── docs/             # Documentation
│   ├── decisions/    # Architecture decision records
│   ├── research/     # Research notes
│   ├── mcp/          # MCP server docs
│   └── deployment/   # Deployment guides
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

## Environment Variables

See `.env.example` for required configuration:
- `DISCORD_BOT_TOKEN` - Discord bot token
- `DISCORD_USER_ID` - Your Discord user ID (whitelist)
- `CLAUDE_API_KEY` - Anthropic API key
- `TODOIST_API_TOKEN` - Todoist API token
- `GITHUB_TOKEN` - GitHub personal access token
- `READWISE_API_KEY` - Readwise API key
- `LETTA_CONFIG` - Letta configuration
- `OBSIDIAN_MCP_URL` - URL to Obsidian MCP server
- `OBSIDIAN_MCP_TOKEN` - Auth token for Obsidian MCP

## Features

### MVP (Current Phase)
- [x] Project scaffolding (mise, uv, Docker, pre-commit)
- [ ] Discord bot with user authentication
- [ ] Slash commands (`/daily`, `/idea`)
- [ ] Natural conversation with context
- [ ] Todoist integration
- [ ] Obsidian integration
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

## Related

- [Obsidian Vault Project Notes](../Obsidian/akashic-vault/Spaces/Efforts/Works-from-anywhere%20Assistant/)
- [Original Idea Seed](../Obsidian/akashic-vault/Bins/Ideas/Works-from-anywhere%20AI%20assistant.md)
