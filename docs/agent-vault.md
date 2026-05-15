# Agent Vault Integration

[Agent Vault](https://github.com/Infisical/agent-vault) is an open-source credential broker by [Infisical](https://infisical.com) that sits between AI agents and the APIs they call. It prevents credential exfiltration via prompt injection by ensuring agents never hold real credentials.

## Why use Agent Vault with Tesco MCP?

Tesco MCP currently uses **public endpoints only** — no authentication required for product search, nutrition data, and price comparison. Agent Vault is not needed for these features.

However, future versions will add **authenticated features** that require a Tesco account:

- 🛒 Cart management (add, view, remove items)
- 📦 Order history
- 🚚 Delivery slot checking and booking
- ⭐ Favourites and frequent purchases

These features require Tesco session cookies. Passing real session cookies through an AI agent is a security risk — a prompt injection attack could exfiltrate them.

## How it works

```
AI Agent (Claude, OpenClaw, etc.)
    │
    │  Cookie: __tesco_session__  (dummy)
    │
    ▼
┌──────────────┐
│  Agent Vault  │  intercepts request, swaps
│              │  __tesco_session__ → real cookie
└──────┬───────┘
       │
       ▼
  xapi.tesco.com  (authenticated request)
```

1. Your agent sends requests with a **dummy credential** (`__tesco_session__`)
2. Agent Vault intercepts the outbound HTTPS request
3. Agent Vault replaces the dummy credential with the **real Tesco session cookie**
4. The request reaches Tesco with valid authentication
5. The agent **never sees the real cookie**

## Setup

### 1. Install Agent Vault

Agent Vault runs on a **separate host** from your agent. See the [installation guide](https://docs.agent-vault.dev/installation) for full options.

```bash
# Install the CLI on your agent's machine
curl --proto '=https' --proto-redir '=https' --tlsv1.2 -fsSL https://get.agent-vault.dev | sh
```

### 2. Configure a vault with Tesco credentials

In the Agent Vault management UI (port 14321), create a vault with service rules for Tesco's API endpoints. Configure credential substitution so that requests to `xapi.tesco.com` and `search.api.tesco.com` have the dummy cookie replaced with a real Tesco session cookie.

### 3. Create an agent token

In Agent Vault, create an agent and obtain a token (`av_agt_xxx`). This token authenticates your agent to the vault without exposing any upstream credentials.

### 4. Run your agent through Agent Vault

```bash
export AGENT_VAULT_ADDR="http://<vault-host>:14321"
export AGENT_VAULT_TOKEN="av_agt_xxx"
export AGENT_VAULT_VAULT="<VAULT_NAME>"

# agent-vault run wraps your process with HTTPS_PROXY set automatically
agent-vault run -- python -m tesco_mcp.server
```

Or in Docker:

```dockerfile
COPY --from=infisical/agent-vault:latest /usr/local/bin/agent-vault /usr/local/bin/agent-vault
ENTRYPOINT ["agent-vault", "run", "--", "python", "-m", "tesco_mcp.server"]
```

```bash
docker run --rm \
  -e AGENT_VAULT_ADDR="http://<vault-host>:14321" \
  -e AGENT_VAULT_TOKEN="av_agt_xxx" \
  -e AGENT_VAULT_VAULT="<VAULT_NAME>" \
  your-tesco-mcp-image
```

The `agent-vault run` command sets `HTTPS_PROXY` and `HTTP_PROXY` automatically so all outbound HTTP calls route through Agent Vault for credential injection.

## Current status

| Feature | Auth required | Agent Vault needed |
|---------|:---:|:---:|
| Search products | ❌ | ❌ |
| Get nutrition | ❌ | ❌ |
| Compare products | ❌ | ❌ |
| Find promotions | ❌ | ❌ |
| Find alternatives | ❌ | ❌ |
| Meal cost calculator | ❌ | ❌ |
| Weekly shop estimator | ❌ | ❌ |
| Cart management | ✅ | ✅ Recommended |
| Order history | ✅ | ✅ Recommended |
| Delivery slots | ✅ | ✅ Recommended |

## Learn more

- [Agent Vault documentation](https://docs.agent-vault.dev/)
- [Agent Vault GitHub](https://github.com/Infisical/agent-vault)
- [Custom agent quickstart](https://docs.agent-vault.dev/quickstart/custom-agent)
- [Infisical](https://infisical.com)
