# Agent Vault Integration

[Agent Vault](https://github.com/Infisical/agent-vault) is an open-source credential broker by [Infisical](https://infisical.com) that sits between AI agents and the APIs they call. It prevents credential exfiltration via prompt injection by ensuring agents never hold real credentials.

## Why use Agent Vault with Tesco MCP?

Tesco MCP v1 uses **public endpoints only** — no authentication required for product search, nutrition data, and price comparison. Agent Vault is not needed for these features.

However, future versions (v2+) will add **authenticated features** that require a Tesco account:

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

```bash
# Docker
docker run -d --name agent-vault \
  -p 14321:14321 -p 14322:14322 \
  infisical/agent-vault:latest

# Or binary
curl -fsSL https://raw.githubusercontent.com/Infisical/agent-vault/main/install.sh | bash
```

### 2. Configure credential substitution

Add a service rule for Tesco's API endpoints:

```yaml
# agent-vault.yaml
services:
  - name: tesco-api
    hosts:
      - "xapi.tesco.com"
      - "search.api.tesco.com"
    credentials:
      - type: header
        header_name: Cookie
        dummy_value: "__tesco_session__"
        real_value_env: "TESCO_SESSION_COOKIE"
```

### 3. Configure your agent

Set the `HTTPS_PROXY` environment variable so your agent routes traffic through Agent Vault:

```bash
export HTTPS_PROXY=http://localhost:14322
export TESCO_SESSION_COOKIE="your-real-tesco-session-cookie"
```

### 4. Use dummy credentials in Tesco MCP

When authenticated features are available, the MCP server will use `__tesco_session__` as the cookie value. Agent Vault transparently swaps it before the request reaches Tesco.

## Current status

| Feature | Auth required | Agent Vault needed |
|---------|:---:|:---:|
| Search products | ❌ | ❌ |
| Get nutrition | ❌ | ❌ |
| Compare products | ❌ | ❌ |
| Find promotions | ❌ | ❌ |
| Meal cost calculator | ❌ | ❌ |
| Cart management | ✅ | ✅ Recommended |
| Order history | ✅ | ✅ Recommended |
| Delivery slots | ✅ | ✅ Recommended |

## Learn more

- [Agent Vault documentation](https://docs.agent-vault.dev/)
- [Agent Vault GitHub](https://github.com/Infisical/agent-vault)
- [Infisical](https://infisical.com)
