# Memory MCP Server

An MCP (Model Context Protocol) server that allows Claude Code to search and read your local conversation history.

> **For Claude**: See [USAGE_GUIDE.md](./USAGE_GUIDE.md) for detailed guidance on when and how to use this tool effectively.

## Features

- **Search conversations** - Full-text search across all your Claude Code chats (returns excerpts)
- **Get full conversations** - Retrieve complete conversation by session ID (use sparingly)
- **List recent chats** - Get your most recent conversations with summaries
- **Project filtering** - Search within specific projects
- **Minimal context usage** - Smart design returns small excerpts first, full content only when needed

## Installation

```bash
# Navigate to the server directory
cd tools/servers/memory

# Install dependencies (if not already installed)
./venv/bin/pip install -r requirements.txt
```

## Configuration

Add this server to Claude Code:

```bash
claude mcp add memory "/Users/kate/Projects/takuma-os/tools/servers/memory/run.sh"
```

Or manually edit `~/.claude/settings.json`:

```json
{
  "mcpServers": {
    "memory": {
      "command": "/Users/kate/Projects/takuma-os/tools/servers/memory/run.sh"
    }
  }
}
```

## Available Tools

### search_conversations
Search through all Claude Code conversations.

Parameters:
- `query` (required): Search text
- `project` (optional): Limit to specific project
- `includeAssistant` (optional): Include assistant responses (default: false)
- `limit` (optional): Max results (default: 20)

Example:
```
Search for: "time management pivot"
In project: "-Users-kate-Projects-takuma-os"
```

### get_conversation
Retrieve a complete conversation by session ID.

Parameters:
- `sessionId` (required): The conversation session ID

Example:
```
Get conversation: "be8bb112-4041-4fc8-82a5-5e0c0e006364"
```

### list_recent
List your most recent conversations.

Parameters:
- `limit` (optional): Number of conversations (default: 10)

### list_projects
List all available Claude Code projects.

## Data Location

The server reads from your Claude Code conversation history stored at:
```
~/.claude/projects/
```

Each project has its own subdirectory containing JSONL files for each conversation.

## Privacy & Security

- All data stays local on your machine
- No external API calls or data transmission
- Read-only access to conversation files
- Runs entirely within your Claude Code environment

## Development

```bash
# Run in development mode (with hot reload)
npm run dev

# Build for production
npm run build

# Start production server
npm start
```

## Conversation Structure

Claude Code stores conversations in JSONL format with entries like:
- `type: "user"` - User messages
- `type: "assistant"` - Claude's responses
- `type: "summary"` - Conversation summaries
- `type: "system"` - System metadata

Each entry contains:
- `timestamp` - ISO format timestamp
- `sessionId` - Unique conversation identifier
- `message` - The actual content
- `uuid` - Unique message identifier

## Example Usage in Claude Code

Once configured, you can ask Claude:
- "Search my history for conversations about time management"
- "Find when we discussed the pivot from money to time"
- "Show me recent conversations about Kane"
- "Get the full conversation from session be8bb112-4041-4fc8-82a5-5e0c0e006364"

## Troubleshooting

If the server doesn't work:
1. Check that `~/.claude/projects/` exists and contains JSONL files
2. Verify the server path in settings.json is correct
3. Restart Claude Code after adding the MCP server
4. Check Claude Code logs for any error messages

## License

Part of Takuma OS - internal tool for Kate's projects.