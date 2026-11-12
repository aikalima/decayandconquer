---
name: decay-theta-plays
description: Use the Decay And Conquer Theta Plays MCP server to inspect locally computed options premium scans, ranked theta candidates, and quote-quality diagnostics.
compatibility: Requires an MCP-capable host and a local checkout of /Users/markus/src/decay_core with backend dependencies installed. No authentication is required for local use.
license: MIT
metadata:
  mcp_servers: '{"decay-theta-plays":{"command":"/Users/markus/src/decay_core/scripts/start-theta-mcp.sh","auth":"none","transport":"stdio"},"decay-theta-plays-http":{"url":"http://127.0.0.1:6181/mcp","auth":"none","transport":"streamable-http"}}'
  author: decay-and-conquer
  version: 0.1.0
  category: finance
  keywords: options,theta,iv,hv,duckdb,mcp,decay-and-conquer
---

# Decay Theta Plays

Use this skill when the user asks about Decay And Conquer Theta Plays, options premium scans, IV/HV rankings, expensive calls, expensive puts, or quote-quality diagnostics.

The MCP server is read-only. It reads local DuckDB theta scan tables and does not place trades, fetch private brokerage data, or require authentication.

## Installation

If the host supports Agent Skills, install this skill by copying this folder into the host's skills directory or by asking the host to read this `SKILL.md` and install it.

Then configure the MCP server.

### Claude Desktop stdio config

Add this to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "decay-theta-plays": {
      "command": "/Users/markus/src/decay_core/scripts/start-theta-mcp.sh"
    }
  }
}
```

Restart Claude Desktop after editing the config.

### Local HTTP config

If the Decay app is already running with MCP endpoints:

```bash
cd /Users/markus/src/decay_core
scripts/start-all.sh --with-mcp
```

Use this MCP URL in clients that support streamable HTTP MCP:

```text
http://127.0.0.1:6181/mcp
```

## Available Tools

- `list_theta_expiries` lists configured and scanned expiries, including scan freshness.
- `get_theta_plays` returns ranked rows for `highest_premium`, `expensive_calls`, or `expensive_puts`.
- `get_theta_play_detail` returns one ticker's row, diagnostics, and interpretation.

## Usage Guidance

Prefer `list_theta_expiries` first when the user did not specify an expiry.

Use `get_theta_plays` for broad questions such as:

- "Show me the top theta plays for the next scanned monthly expiration."
- "Which puts look most expensive?"
- "What are the best iron condor candidates?"

Use `get_theta_play_detail` when the user asks about one ticker or when a row looks suspicious.

Always mention scan freshness. Treat high IV/HV premium as a screening signal, not a recommendation. Pay attention to `quality_score`, `price_source`, open interest, bid/ask spread diagnostics, IV skew, and put-call parity warnings before interpreting a candidate.
