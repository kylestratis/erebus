# Todoist MCP Integration

Erebus integrates with Todoist via the official [Todoist AI MCP server](https://github.com/Doist/todoist-ai) for task management capabilities.

## Configuration

### Environment Variable

Set your Todoist API token in `.env`:

```bash
TODOIST_API_TOKEN=your_todoist_api_token_here
```

Get your API token from: https://todoist.com/app/settings/integrations/developer

### How It Works

1. On bot startup, `ErebusBot._setup_mcp()` initializes the MCP client
2. The Todoist MCP server is spawned as a subprocess via `npx @doist/todoist-ai`
3. Tools are discovered and registered with the conversation manager
4. Claude can then use these tools when responding to user messages

## Available Tools

The Todoist MCP server provides these tools (prefixed with `todoist_` in Erebus):

| Tool | Description |
|------|-------------|
| `todoist_get_tasks` | Retrieve tasks with optional filters |
| `todoist_add_task` | Create a new task |
| `todoist_update_task` | Modify an existing task |
| `todoist_close_task` | Mark a task as complete |
| `todoist_delete_task` | Permanently delete a task |
| `todoist_get_projects` | List all projects |
| `todoist_add_project` | Create a new project |

## Example Interactions

### Querying Tasks

> **User:** What tasks do I have due today?
>
> **Erebus:** *Uses `todoist_get_tasks` with today filter*
>
> You have 3 tasks due today:
> - Buy groceries (priority 2)
> - Review PR #42 (priority 1)
> - Call dentist (priority 4)

### Creating Tasks

> **User:** Add a task to buy milk tomorrow
>
> **Erebus:** *Uses `todoist_add_task`*
>
> Created task "Buy milk" due tomorrow.

### Completing Tasks

> **User:** Mark "Buy groceries" as done
>
> **Erebus:** *Uses `todoist_close_task`*
>
> Marked "Buy groceries" as complete.

## Architecture

```
Discord User
     │
     ▼
 ErebusBot (Discord client)
     │
     ▼
 ConversationManager
     │
     ▼
 Claude API (with tools)
     │
     ▼
 MCPClientManager
     │
     ▼
 Todoist MCP Server (subprocess)
     │
     ▼
 Todoist API
```

## Error Handling

- **Connection failures**: Bot continues without Todoist tools; AI responds but can't manage tasks
- **Tool execution errors**: Error message returned to Claude, which informs the user
- **Rate limiting**: Todoist API has rate limits; errors are logged and reported to user
- **Timeouts**: Tool calls timeout after 30 seconds (configurable via `AgentConfig.tool_call_timeout`)

## Troubleshooting

### Tools not appearing

1. Check `TODOIST_API_TOKEN` is set correctly
2. Verify npx can run: `npx @doist/todoist-ai --help`
3. Check bot logs for MCP connection errors

### Authentication errors

1. Regenerate your API token at Todoist settings
2. Ensure token has no extra whitespace
3. Check token permissions

### Slow responses

- Tool calls add latency (network round-trips to Todoist API)
- Consider the agent loop: multiple tool calls = multiple API calls
- Check `AgentConfig.max_tool_iterations` if stuck in loops

## Security Considerations

- API token stored in environment variable, never in code
- Token passed to subprocess via environment, not command line
- Only whitelisted Discord users can trigger tool calls
- All tool executions are logged for audit
- Destructive operations (complete/delete) require user confirmation before execution
