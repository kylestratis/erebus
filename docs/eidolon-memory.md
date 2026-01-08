# EidolonMemory System

EidolonMemory is the stateful memory backend for Erebus, powered by [Letta](https://letta.com/). It enables persistent learning across sessions through a three-tier memory architecture.

## Architecture Overview

```
Discord Bot
    │
    ▼
EidolonMemory (wrapper)
    │
    ▼ REST API
Letta Server (Docker)
    ├── Agent per user
    │   ├── Core Memory (persona, human profile)
    │   ├── Archival Memory (learned patterns)
    │   └── Recall Memory (conversation history)
    │
    ├── Tools
    │   ├── Vault tools (Obsidian operations)
    │   └── Todoist MCP (task management)
    │
    └── PostgreSQL (state persistence)
```

## Memory Tiers

### Core Memory (Always in Context)

Core memory blocks are always visible to the agent, similar to RAM. They're actively managed by the agent using built-in tools.

**Blocks:**
- `persona` - Erebus identity and voice
- `human` - User profile (name, timezone, preferences)
- `context` - Current session state

### Archival Memory (Semantic Search)

Out-of-context storage for large-scale information. Semantically searchable using embeddings.

**Contents:**
- Learned preferences
- Task patterns
- Note-taking habits
- Historical summaries

### Recall Memory (Conversation History)

Automatic persistence of complete interaction history, searchable via `conversation_search` tool.

## Setup

### Prerequisites

- Docker and Docker Compose
- Python 3.11+
- Anthropic API key (for Claude)
- OpenAI API key (for embeddings)

### Start Letta Server

```bash
cd docker/letta
docker compose up -d
```

This starts:
- Letta server on port 8283
- PostgreSQL for persistence

### Configure Environment

Add to your `.env`:

```bash
# Letta server
LETTA_API_URL=http://localhost:8283
LETTA_API_KEY=  # Optional for local server

# Required by Letta for model access
ANTHROPIC_API_KEY=your-anthropic-key
OPENAI_API_KEY=your-openai-key  # For embeddings
```

### Verify Connection

```bash
curl http://localhost:8283/health
```

## Usage

### Agent Per User

Each Discord user gets their own Letta agent. Agents are created on first interaction and persist indefinitely.

```python
from agents.eidolon import EidolonMemory

eidolon = EidolonMemory(
    base_url="http://localhost:8283",
    api_key=None,  # Optional for local
)

# Get or create agent for user
agent_id = await eidolon.get_or_create_agent(user_id=123456789)

# Send message
response = await eidolon.chat(user_id=123456789, message="Hello!")
```

### Memory Persistence

All state is automatically checkpointed to PostgreSQL:
- Survives bot restarts
- Survives Letta server restarts
- Can be queried across agents

## Configuration Reference

### Memory Blocks

The persona block captures Erebus's voice:

```
You are Erebus, a personal AI assistant that operates through Discord.

Your personality:
- You are helpful, concise, dark, and occasionally dry-witted
- You respect the user's time and get to the point
- You're knowledgeable but admit when you don't know something
- You have a subtle, mysterious aesthetic
```

The human block is templated and evolves:

```
Name: {user_name}
Timezone: {timezone}
Work patterns: [learned from interactions]
Preferences: [accumulated observations]
```

### Tools Available to Agents

**Native Tools** (executed by the bot):
- `vault_read_note` - Read note content
- `vault_write_note` - Create/update notes
- `vault_search_notes` - Search vault
- `vault_get_daily_note` - Get daily note
- `vault_create_daily_note` - Create from template
- `vault_delete_note` - Delete a note

Native tools run in the bot process because they need access to the local Obsidian vault filesystem.

**MCP Tools** (executed by Letta):
- Todoist tools via MCP server

MCP tools are configured in the Letta server and executed directly by Letta.

### Tool Execution Architecture

```
User Message → Letta Agent
                    │
                    ├─→ Native tool call? → Bot executes → Result back to Letta
                    │
                    └─→ MCP tool call? → Letta executes directly
                                ↓
                          Final Response
```

## Troubleshooting

### Letta Server Won't Start

Check Docker logs:
```bash
docker compose -f docker/letta/docker-compose.yml logs letta
```

Common issues:
- PostgreSQL not ready: Wait for health check
- Port 8283 in use: Change in docker-compose.yml
- Missing API keys: Check environment variables

### Agent Not Remembering

1. Verify Letta server is running
2. Check PostgreSQL has data: `docker exec erebus-postgres psql -U letta -c "SELECT count(*) FROM agents;"`
3. Ensure same agent ID is being used across sessions

### Tools Not Working

1. Verify tools are registered with agent
2. Check Letta logs for errors
3. Test tool directly via Letta API

## Data Management

### Backup

PostgreSQL data is in Docker volume `erebus-letta-data`:

```bash
docker exec erebus-postgres pg_dump -U letta letta > backup.sql
```

### Restore

```bash
cat backup.sql | docker exec -i erebus-postgres psql -U letta letta
```

### Export Agent

Letta supports agent export in `.af` format for portability.
