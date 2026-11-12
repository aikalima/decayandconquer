---
name: decay-predictions
description: Use the Decay And Conquer Prediction MCP server to run local options-derived stock price forecasts and compact historical backtests.
compatibility: Requires an MCP-capable host and a local checkout of /Users/markus/src/decay_core with backend dependencies installed. No authentication is required for local use.
license: MIT
metadata:
  mcp_servers: '{"decay-predictions":{"command":"/Users/markus/src/decay_core/scripts/start-prediction-mcp.sh","auth":"none","transport":"stdio"},"decay-predictions-http":{"url":"http://127.0.0.1:6182/mcp","auth":"none","transport":"streamable-http"}}'
  author: decay-and-conquer
  version: 0.1.0
  category: finance
  keywords: options,prediction,backtest,forecast,duckdb,mcp,decay-and-conquer
---

# Decay Predictions

Use this skill when the user asks about Decay And Conquer Backtest & Forecast, options-derived price distributions, probability of a stock reaching a target price, or historical backtest calibration.

The MCP server is read-only. It uses local DuckDB options data and does not place trades, fetch private brokerage data, or require authentication.

## Installation

If the host supports Agent Skills, install this skill by copying this folder into the host's skills directory or by asking the host to read this `SKILL.md` and install it.

Then configure the MCP server.

### Claude Desktop stdio config

Add this to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "decay-predictions": {
      "command": "/Users/markus/src/decay_core/scripts/start-prediction-mcp.sh"
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
http://127.0.0.1:6182/mcp
```

## Available Tools

- `get_prediction_defaults` returns date-aware prediction defaults and local DuckDB stats.
- `run_prediction` runs a single-day or observation-window forecast and returns compact distribution statistics.
- `run_backtest` runs a compact local backtest over explicit historical observation dates.

## Usage Guidance

Use `get_prediction_defaults` first when the user did not specify dates.

Use `run_prediction` for questions such as:

- "What are the chances SPY finishes at least 10% above its observation-date price at the next monthly expiration?"
- "Forecast NVDA using the latest observation window."
- "Compare the distribution for AAPL with a target date next month."

Use `run_backtest` when the user asks how well the model performed historically. Provide explicit observation dates when possible.

Always explain that forecasts are options-implied probability distributions, not investment advice. Report the observation window, target date, expiry used, data freshness, median, mean, 5th/95th percentiles, and realized price/backtest error when available.
