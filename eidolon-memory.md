# EidolonMemory System

EidolonMemory is the stateful memory backend for Erebus, powered by [Letta](https://letta.com/). It enables persistent learning across sessions through a hierarchical memory architecture based on the [MemGPT research paper](https://arxiv.org/abs/2310.08560).

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
    │   ├── Core Memory (persona, human profile, context)
    │   ├── Archival Memory (learned patterns - vector DB)
    │   └── Recall Memory (conversation history)
    │
    ├── Tools
    │   ├── Native tools (Vault operations - bot-side)
    │   └── MCP tools (Todoist - Letta-side)
    │
    ├── Sleep-time Agent (optional)
    │   └── Background memory refinement
    │
    └── PostgreSQL + pgvector (state persistence)
```

## Core Concepts

### The MemGPT Paradigm

Letta implements the "LLM Operating System" concept from MemGPT:

- **Memory hierarchy**: Divides memory into in-context (always visible) and out-of-context (retrieved on demand)
- **Active management**: Agents don't just read memory—they actively decide what to remember, update, and search for
- **Context as RAM**: The context window is a scarce resource; effective memory management decides what stays in context vs. external storage

This differs from traditional RAG systems that passively retrieve information. Letta agents autonomously manage their own memory state.

## Memory Tiers

### Core Memory (In-Context / "RAM")

Memory blocks are structured sections **always visible** in the agent's context window. No retrieval needed—they persist across all interactions.

**Erebus Blocks:**
- `persona` - Agent identity, voice, and behavioral guidelines
- `human` - User profile (name, timezone, preferences—evolves over time)
- `context` - Current session state, active projects, pending items

**Key property**: Agents can learn to use blocks with any label. You could add `projects`, `goals`, or `relationships` blocks for domain-specific memory.

**Built-in memory tools**:
- `memory_replace` - Precise search-and-replace edits within a block
- `memory_insert` - Add lines to a block
- `memory_rethink` - Rewrite an entire block from scratch

### Archival Memory (Out-of-Context / "Disk")

External storage for large-scale information that doesn't need constant visibility. Backed by a vector database (pgvector) for semantic search.

**Characteristics:**
- Scales to millions of entries without increasing token usage
- Semantically searchable via embeddings
- Persists across conversations and restarts
- Agent-managed via tools

**Built-in tools**:
- `archival_memory_insert` - Store information for later retrieval
- `archival_memory_search` - Semantic search across stored memories

**Use cases:**
- Learned user preferences and patterns
- Task completion history
- Note-taking habits
- Historical summaries and insights

### Recall Memory (Conversation History)

Complete interaction history, automatically persisted and searchable.

**Built-in tools**:
- `conversation_search` - Full-text and semantic search across past messages
- `conversation_search_date` - Search by date range

**Note**: Unlike core memory (always visible), recall memory requires explicit retrieval. The agent decides when to search past conversations for context.

## Memory Best Practices

**Core memory excels for:**
- Always-visible information (persona, preferences)
- Evolving knowledge that changes frequently
- Information needed in every interaction

**Archival memory suits:**
- Large document collections
- Historical logs and patterns
- Static reference material
- Information retrieved occasionally

**Combine both**: Use core memory as an "executive summary" while archival memory holds complete details. For example, core memory might note "User prefers morning meetings" while archival memory stores specific scheduling patterns.

## Sleep-time Agents

Sleep-time agents are background processes that share memory with the primary agent but run asynchronously. They enable "sleep-time compute"—using idle time to process and refine memory.

### How It Works

1. Primary agent handles conversations normally
2. Every N interactions (default: 5), the sleep-time agent wakes
3. Sleep-time agent reviews recent context and updates memory blocks
4. Changes propagate to primary agent on next interaction

### Benefits

- **Non-blocking**: Memory refinement doesn't slow down conversations
- **Proactive learning**: Memory is reorganized during idle periods, not just incrementally during chats
- **Higher quality**: Sleep-time agent can use slower, more capable models since latency doesn't matter

### Configuration

```python
# Enable when creating agent
agent = await client.agents.create(
    name="erebus-user123",
    enable_sleeptime=True,
    # ...
)

# Adjust frequency (default: 5 steps)
await client.groups.update(group_id, {
    "manager_config": {"sleeptime_agent_frequency": 10}
})
```

### Model Selection

Since sleep-time agents aren't latency-constrained, you can use stronger models:
- Primary agent: Fast model (e.g., `claude-sonnet-4`)
- Sleep-time agent: Stronger model (e.g., `claude-opus-4`)

**Status**: Not yet implemented in Erebus. See implementation plan for future integration.

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
- PostgreSQL with pgvector for persistence and semantic search

### Configure Environment

Add to your `.env`:

```bash
# Letta server
LETTA_API_URL=http://localhost:8283
LETTA_API_KEY=  # Optional for local server

# Required by Letta for model access
ANTHROPIC_API_KEY=your-anthropic-key
OPENAI_API_KEY=your-openai-key  # For embeddings

# For native MCP support (see MCP Architecture section)
TODOIST_API_KEY=your-todoist-key
```

### Verify Connection

```bash
curl -sL http://localhost:8283/health
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

## Tool Architecture

### Tool Categories

**Native Tools** (executed by the bot):
- `vault_read_note` - Read note content
- `vault_write_note` - Create/update notes
- `vault_search_notes` - Search vault
- `vault_get_daily_note` - Get daily note
- `vault_create_daily_note` - Create from template
- `vault_delete_note` - Delete a note
- `system_status` - Introspect available tools and jobs

Native tools run in the bot process because they need access to local resources (Obsidian vault filesystem). They're registered as stub functions in Letta with `default_requires_approval=True`, causing Letta to return approval requests instead of executing. The bot intercepts these, executes locally, and sends results back.

**MCP Tools** (Todoist, GitHub, etc.):

Two execution models are available:

1. **Current: Bot-side execution** - MCP client runs in bot process, tools routed through `MCPToolExecutor`
2. **Future: Letta-side execution** - MCP servers registered directly with Letta via `mcp_servers.create()`

### Current Tool Execution Flow

```
User Message → Letta Agent
                    │
                    ├─→ Tool call with requires_approval=True
                    │
                    ▼
              Bot intercepts
                    │
                    ├─→ Native tool? → Execute locally
                    │
                    └─→ MCP tool? → Route through MCPToolExecutor
                                │
                                ▼
                          Execute via MCP client
                                │
                                ▼
                          Send result back to Letta
                                │
                                ▼
                          Final Response
```

### Native MCP Support (Migration Target)

Letta supports registering MCP servers directly, eliminating the bot-side wrapper:

```python
# Register Todoist MCP server with Letta
await client.mcp_servers.create(
    server_name="todoist",
    config={
        "mcp_server_type": "stdio",
        "command": "npx",
        "args": ["@doist/todoist-ai"],
        "env": {"TODOIST_API_KEY": os.environ["TODOIST_API_KEY"]},
    }
)
```

**Supported transport types:**
- `stdio` - Local subprocess (Docker only)
- `sse` - Server-Sent Events over HTTP
- `streamable_http` - Streamable HTTP

**Constraint**: `stdio` transport only works when Letta runs in Docker. The Letta API (cloud) does not support stdio—use HTTP-based transports instead.

**Benefits of native MCP:**
- Cleaner architecture (Letta handles MCP lifecycle)
- Consistent tool execution path
- No bot-side MCP client needed for those tools

**Migration steps:**
1. Add `TODOIST_API_KEY` to Letta Docker container environment
2. Register Todoist MCP server via `client.mcp_servers.create()`
3. Remove `MCPToolExecutor` wrapper from bot
4. Update tool registration to exclude MCP tools from native registry

**Status**: See implementation plan for migration timeline.

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

## References

- [Letta Documentation](https://docs.letta.com/)
- [Memory Overview](https://docs.letta.com/guides/agents/memory/)
- [Understanding Memory Management](https://docs.letta.com/advanced/memory-management/)
- [Core Memory](https://docs.letta.com/guides/ade/core-memory/)
- [Archival Memory](https://docs.letta.com/guides/agents/archival-memory/)
- [Sleep-time Agents](https://docs.letta.com/guides/agents/architectures/sleeptime/)
- [Sleep-time Compute Blog](https://www.letta.com/blog/sleep-time-compute)
- [MCP Overview](https://docs.letta.com/guides/mcp/overview/)
- [Local MCP Servers](https://docs.letta.com/guides/mcp/local/)
- [MCP Server API](https://docs.letta.com/api/resources/mcp_servers/methods/create/)
- [MemGPT Paper](https://arxiv.org/abs/2310.08560)
- [Agent Memory Blog](https://www.letta.com/blog/agent-memory)
