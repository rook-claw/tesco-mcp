# Tesco MCP v2 — Authenticated Features Design

> Based on reverse-engineering uk-grocery-cli's Tesco provider (Mar 2026).
> All endpoints/queries below are publicly documented in that project's source.

## Auth model

Tesco uses cookie-based session auth with Akamai bot detection on the login page.

**Two paths to obtain a session:**

1. **Playwright login (semi-automated)** — non-headless browser, anti-bot flags, user solves any CAPTCHA/OTP challenge manually. ~60s.
2. **Import session (reliable)** — user logs in via real Chrome, exports cookies (Cookie Editor extension or DevTools), passes JSON to MCP. Bypasses Akamai entirely.

**Session lifetime:** ~7 days. Stored at `~/.tesco/session.json`.

## API endpoints

| Endpoint | Auth | Purpose |
|----------|:---:|---------|
| `https://search.api.tesco.com/search` | ❌ | Product TPNB search (already used in v1) |
| `https://xapi.tesco.com/` | ✅ | GraphQL — products, basket, slots |
| `https://www.tesco.com/groceries/en-GB/orders` | ✅ | REST — order history |
| `https://www.tesco.com/groceries/en-GB/orders/{id}` | ✅ | REST — order detail |

**Required headers (all requests):**
```
x-apikey: TvOSZJHlEk0pjniDGQFAc9Q59WGAR4dA   (public, already in v1)
language: en-GB                              (en-IE for Ireland — needs testing)
region:   UK                                 (IE for Ireland — needs testing)
Cookie:   <session cookies>
User-Agent: <real browser UA>
Referer:  https://www.tesco.com/groceries/en-GB/
Origin:   https://www.tesco.com
```

## GraphQL operations to port to Python

### Get basket
```graphql
query GetBasket($basketContexts: [BasketContextType]) {
  basket(basketContexts: $basketContexts) {
    id
    splitView {
      id
      totalPrice
      guidePrice
      totalItems
      charges { fulfilment minimumValue }
      items {
        id
        quantity
        cost
        unit
        product { id tpnb gtin title defaultImageUrl price { actual } }
      }
    }
  }
}
```

### Update basket (add/remove/update — single mutation)
```graphql
mutation UpdateBasket($items: [BasketLineItemInputType], $orderId: ID) {
  basket(items: $items, orderId: $orderId) {
    id
    splitView { id totalPrice totalItems items { id quantity cost product { id title } } }
  }
}
# variables:
# { orderId: <basket.id from GetBasket>,
#   items: [{ adjustment: false, id: <tpnc>, newValue: <quantity 0=remove>, newUnitChoice: "pcs" }] }
```

### Delivery slots
```graphql
query DeliverySlots($start: String, $end: String, $type: FulfilmentTypeType) {
  delivery(start: $start, end: $end) {
    id start end charge status group
    price { beforeDiscount afterDiscount }
    locationUuid
  }
  fulfilment(type: $type, range: { start: $start, end: $end }) {
    metadata { preBookedOrderDays }
  }
}
# variables: { start: ISO, end: ISO, type: "DELIVERY_VAN" }
```

### Book slot
```graphql
mutation Fulfilment($slotId: ID!) {
  fulfilment(slotId: $slotId) {
    orderId status error { code message }
  }
}
```

## v2 MCP tools

| Tool | Method | Description |
|------|--------|-------------|
| `import_session` | local | Load cookies from exported JSON file |
| `login_browser` | local | Playwright-driven login (semi-interactive) |
| `session_status` | local | Show login state + days until expiry |
| `get_basket` | GraphQL | Current basket contents + totals |
| `add_to_basket` | GraphQL | Add item by TPNC + quantity |
| `update_basket_item` | GraphQL | Change quantity |
| `remove_from_basket` | GraphQL | Set quantity to 0 |
| `get_delivery_slots` | GraphQL | Available slots in a date range |
| `book_delivery_slot` | GraphQL | Reserve a slot |
| `get_orders` | REST | Order history (paginated) |
| `get_order_detail` | REST | Single order with line items |

## Agent Vault integration

The session cookie is the entire credential surface. Approach:

1. Tesco MCP code uses `Cookie: __tesco_session__` (dummy)
2. Agent Vault intercepts outbound HTTPS to `xapi.tesco.com` + `www.tesco.com`
3. Swaps dummy with the real cookie string from the user's vault
4. Agent never holds the session cookie

**Vault config (user side):**
```bash
# One-time: user logs into Tesco, exports cookies, stores them in vault
agent-vault vault set tesco TESCO_COOKIE "atrc=...; trkid=...; consumer=..."

# Per agent run:
agent-vault run --vault tesco -- python -m tesco_mcp.server
```

## Ireland-specific differences (TBD — needs live testing)

- `region: IE` instead of `UK`
- `language: en-IE`
- Different login domain: `https://www.tesco.ie/` not `tesco.com`
- Different orders path: `https://www.tesco.ie/groceries/en-IE/orders`
- TPNB search already works for IE in v1 with `country: "ie"` param

## Risks & mitigations

| Risk | Mitigation |
|------|-----------|
| Akamai blocks Playwright login | Fall back to `import_session` from real browser cookies |
| Session expires after ~7 days | Surface expiry in `session_status`, prompt re-import |
| GraphQL schema changes | Pin endpoint behaviour with integration tests, fail loudly |
| Cookie leak via agent prompt injection | Agent Vault — agent never sees real cookie |
| Tesco ToS pushback | Public undocumented API, same risk as uk-grocery-cli + Rohlik MCP (no known issues) |

## Build plan (~1 week of evenings)

| Day | Work |
|-----|------|
| 1 | Auth: `import_session` (cookie JSON loader) + `session_status` |
| 2 | GraphQL client refactor: cookie injection + IE/UK header switching |
| 3 | Basket tools: get/add/update/remove |
| 4 | Delivery slot tools: list + book |
| 5 | Orders: list + detail (REST endpoints) |
| 6 | Live IE testing with Conor's account, fix IE-specific quirks |
| 7 | Agent Vault integration doc + example config + release v0.3.0 |

## Source

All endpoint shapes above were extracted from public source code:
- `https://github.com/abracadabra50/uk-grocery-cli/blob/main/src/providers/tesco/api.ts`
- `https://github.com/abracadabra50/uk-grocery-cli/blob/main/src/providers/tesco/auth.ts`
- `https://github.com/abracadabra50/uk-grocery-cli/blob/main/src/providers/tesco/import-session.ts`

License: MIT (same as ours). Attribution recommended in v2 README.
