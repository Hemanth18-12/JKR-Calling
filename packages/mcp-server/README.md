# JKR Calling Native MCP Server

The **JKR Calling Model Context Protocol (MCP)** server allows AI assistants (such as Claude Desktop, Cursor, and Antigravity) to directly manage voice AI agents, dispatch live calls, track coin billing, retrieve transcripts, and generate embeddable website voice widgets.

Unlike closed-source wrappers, this MCP server connects directly to your native JKR Calling platform (Dograh workflow engine, Sarvam Telugu/Hindi/English speech, PostgreSQL & CoinWallet).

---

## Capabilities & Tools

| Tool | Description |
|---|---|
| `jkr_list_agents` | Lists all configured AI agents and versions in your workspace |
| `jkr_get_agent` | Inspects agent prompts, business identities, and voice configurations |
| `jkr_dispatch_call` | Dispatches an outbound AI phone call to any customer via Twilio + Dograh + Sarvam |
| `jkr_get_wallet_balance` | Queries workspace Coin Wallet balance, UPI top-ups, and coin deductions |
| `jkr_list_call_logs` | Fetches recent calls, statuses, durations, and telemetry |
| `jkr_get_call_transcript` | Retrieves full turn-by-turn spoken conversation transcripts |
| `jkr_get_widget_code` | Generates a 1-click HTML/React script tag to embed a voice assistant on any website |

---

## Configuration

### Claude Desktop (`claude_desktop_config.json`)
Add this entry to your `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "jkr-calling": {
      "command": "python",
      "args": ["packages/mcp-server/server.py"],
      "env": {
        "JKR_API_BASE": "http://localhost:8000",
        "JKR_API_KEY": "your_api_key_here"
      }
    }
  }
}
```

### Cursor IDE (`.cursor/mcp.json`)
```json
{
  "mcpServers": {
    "jkr-calling": {
      "command": "python",
      "args": ["packages/mcp-server/server.py"],
      "env": {
        "JKR_API_BASE": "http://localhost:8000"
      }
    }
  }
}
```
