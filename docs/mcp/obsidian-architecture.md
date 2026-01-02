# Obsidian Vault Integration Architecture

This document describes the architecture for Erebus's Obsidian vault integration.

## Overview

The Obsidian integration provides direct file operations for reading, writing, and searching notes in an Obsidian vault. Unlike external MCP servers (like Todoist), vault operations are handled directly in the agents layer as Python code, avoiding subprocess overhead for local file I/O.

The vault is synced to the server via Syncthing, providing near real-time access to notes.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Your Laptop                              │
│  ┌─────────────────┐     ┌─────────────────────────────────┐    │
│  │  Obsidian App   │────▶│        Obsidian Vault           │    │
│  │  (Obsidian Sync)│     │   ~/Obsidian/<VAULT_NAME>/      │    │
│  └─────────────────┘     └───────────────┬─────────────────┘    │
│                                          │                       │
│                          ┌───────────────▼───────────────┐      │
│                          │      Syncthing Daemon         │      │
│                          │        (port 22000)           │      │
│                          └───────────────┬───────────────┘      │
└──────────────────────────────────────────┼──────────────────────┘
                                           │
                              Encrypted P2P Sync
                                           │
┌──────────────────────────────────────────┼──────────────────────┐
│                    DigitalOcean Droplet  │                       │
│                          ┌───────────────▼───────────────┐      │
│                          │      Syncthing Daemon         │      │
│                          │        (port 22000)           │      │
│                          └───────────────┬───────────────┘      │
│                                          │                       │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │              Synced Vault (bidirectional)               │    │
│  │                /data/obsidian/<VAULT_NAME>/             │    │
│  └─────────────────────────────────────────────────────────┘    │
│                              │                                   │
│              ┌───────────────▼───────────────┐                  │
│              │    Vault (Python class)       │                  │
│              │    agents/vault/vault.py      │                  │
│              └───────────────┬───────────────┘                  │
│                              │                                   │
│              ┌───────────────▼───────────────┐                  │
│              │    ConversationManager        │                  │
│              │    (tool execution)           │                  │
│              └───────────────┬───────────────┘                  │
│                              │                                   │
│              ┌───────────────▼───────────────┐                  │
│              │    Erebus Discord Bot         │                  │
│              └───────────────────────────────┘                  │
└─────────────────────────────────────────────────────────────────┘
```

## Why Direct Integration (Not MCP)?

MCP servers make sense for:
- Third-party services (Todoist) we don't control
- Remote services on different machines
- When subprocess isolation is needed

For local file operations on a synced vault:
- **Simpler**: No subprocess, JSON-RPC, or protocol overhead
- **Faster**: Direct file I/O, no IPC latency
- **Debuggable**: Standard Python code
- **Flexible**: Easy to customize template handling

## Sync Strategy

### Syncthing Configuration

- **Laptop**: Source of truth, read-write
- **Server**: Replica, read-write (for bot-created notes)
- **Conflict handling**: Syncthing creates `.sync-conflict` files; bot should avoid editing user files directly
- **Sync direction**: Bidirectional, but bot primarily creates new files

### Sync Considerations

1. **Latency**: Changes sync in near real-time when laptop is online
2. **Offline laptop**: Server has last-synced state; new files queue until laptop reconnects
3. **Conflicts**: Minimize by having bot create new files rather than edit existing ones

## Vault Operations

### Available Operations

| Operation | Description | Risk Level |
|-----------|-------------|------------|
| `read_note` | Read a note by path | Low |
| `write_note` | Create/overwrite a note (with template support) | Medium |
| `search_notes` | Full-text search across vault | Low |
| `list_notes` | List notes in a directory | Low |
| `get_daily_note` | Get today's daily note | Low |
| `create_daily_note` | Create daily note from template | Low |
| `note_exists` | Check if a note exists | Low |

### Configuration

Environment variables:
```bash
OBSIDIAN_VAULT_PATH=/data/obsidian/<VAULT_NAME>
OBSIDIAN_TEMPLATES_PATH=Templates
OBSIDIAN_DAILY_NOTES_PATH=Calendar/Daily Notes
OBSIDIAN_DAILY_NOTE_FORMAT=%Y-%m-%d
```

### Safety Measures

1. **Path validation**: All paths must be within vault root (no directory traversal)
2. **Write confirmation**: Destructive operations require explicit confirmation via system prompt
3. **Backup-friendly**: Bot creates new files; avoids modifying user's existing notes
4. **Template-based**: Notes use templates when available, ensuring consistent format

## Template System

### Template Discovery

Templates are loaded from the configured templates directory (default: `Templates/`).

When creating a note without explicit content, the system:
1. Uses the specified template if provided
2. Auto-detects a matching template based on path (e.g., `Ideas/` → `Idea Seed` template)
3. Falls back to a minimal default

### Template Variables

The vault replaces these placeholders when rendering templates:
- `{{date}}` - Current date (YYYY-MM-DD)
- `{{date:FORMAT}}` - Date with custom strftime format
- `{{time}}` - Current time (HH:MM)
- `{{time:FORMAT}}` - Time with custom strftime format
- `{{title}}` - Note title (passed as variable)
- Custom variables passed during creation

### Example Template

```markdown
---
created: {{date}}
tags:
  - idea-seed
---

# {{title}}

## The Idea

## Why It's Interesting

## Next Steps
```

## Obsidian Syntax Support

The vault understands these Obsidian conventions (for future features):

### Wikilinks
```markdown
[[Note Name]]
[[Note Name|Display Text]]
[[Note Name#Heading]]
[[Note Name#^block-id]]
```

### Block IDs
```markdown
This is a paragraph with a block ID. ^my-block-id
```

### Frontmatter (YAML)
```markdown
---
title: My Note
tags:
  - tag1
created: 2025-01-01
---
```

## File Structure

```
agents/
└── vault/
    ├── __init__.py      # Exports
    └── vault.py         # Vault class, config, operations
```

## Integration with ConversationManager

The `Vault` class will be integrated with the conversation system to expose vault operations as tools for Claude. This will be done by:

1. Creating tool definitions that wrap vault methods
2. Registering tools alongside MCP tools (Todoist)
3. Executing vault operations directly (no subprocess)

## Security Considerations

1. **No secrets in vault**: Vault may contain personal notes but no credentials
2. **Path sandboxing**: Vault class validates all paths stay within root
3. **Syncthing encryption**: Data encrypted in transit between devices
4. **Bot authorization**: Only whitelisted Discord users can trigger vault operations
5. **Audit logging**: All vault operations logged

## Future Enhancements

- [ ] File watching for real-time sync status
- [ ] Conflict detection and notification
- [ ] Graph/backlink analysis
- [ ] Tag-based queries
- [ ] Dataview query execution
- [ ] Wikilink resolution
