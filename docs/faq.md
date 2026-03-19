# FAQ

## What problem does this project solve?

It provides an email-native customer-service agent for dispensaries. The agent can track one email thread at a time, answer store-owned policy questions, and check order status through a pluggable provider layer.

## Is it Dutchie-specific?

No. The public tool contracts are provider-agnostic:

- `lookup_order`
- `search_store_knowledge`

Dutchie is one built-in live order adapter, alongside Treez. The core runtime can also use manual JSON files, a generic bridge service, the Jane bridge path, or a custom Python order provider.

## Is Jane supported?

Yes, but in this repo Jane is bridge-backed rather than direct API-backed.

- Use `ORDER_PROVIDER=jane`
- Point `JANE_BRIDGE_URL` at your merchant-operated Jane lookup service

That bridge should translate Jane-specific auth and payloads into the Mailroom order result contract.

## What tools are exposed to the model?

Exactly two:

- `lookup_order`
- `search_store_knowledge`

There is no model-callable Gmail access, web search, or order mutation.

## What is the difference between `google_api` and `gog`?

- `google_api` polls Gmail directly through the Gmail API.
- `gog` uses `gog` for Gmail watch/send and receives messages through `POST /hooks/gmail`.

The CX tool surface is the same in both modes.

## Can I use this without a vendor integration?

Yes.

- Use `ORDER_PROVIDER=manual` with `MANUAL_ORDER_FILE`
- Use `KNOWLEDGE_PROVIDER=manual` with `STORE_KNOWLEDGE_FILE`

That is the default local-development path.

## Can I plug in my own order system?

Yes. Set:

```bash
ORDER_PROVIDER=custom
ORDER_PROVIDER_FACTORY=your_module:build_provider
```

The factory should return an object with a `lookup(...)` method matching the built-in contract.

## Does the model have direct Gmail access?

No. Gmail transport stays application-owned. The model only sees normalized email text and can call the application-defined tool list.

## Can the agent cancel or edit orders?

No. The current runtime is read-only for customer operations.

## Can the agent answer all policy questions by itself?

Only if the answer exists in the configured store knowledge file. The runtime intentionally avoids live web search for customer replies because store policy and compliance details should come from store-owned data.

## What happens if I delete `state.db`?

You lose:

- thread continuity
- processed-message dedupe history
- dead-letter records
- outbound send-tracking metadata
- cached inbound message snapshots

The schema will be recreated on startup, but the runtime starts cold.

## Can I replay a failed message?

Yes. Use `POST /dead-letter/requeue/{message_id}`. In `gog` mode, replay depends on a cached `inbound_messages` snapshot because that provider does not refetch by ID.
