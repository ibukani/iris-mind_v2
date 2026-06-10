# Identity and Space Semantics

This document defines the stable identity and space terms used by the Iris runtime.

## Account

An Account represents an external provider account binding, not the person itself.

Examples:

- `cli:local-user-id`
- `discord:discord-user-id`
- `github:github-user-id`
- `web:web-user-id`

The natural key is `provider + provider_subject`. `display_name` is mutable,
display-only data and must never be used as an identity key. `account_id` is an
Iris-internal ID. Multiple Accounts may be linked to one Actor.

## Actor

Actor is the Iris-internal subject. It is the primary scope for long-term memory,
relationship state, future persona patches, and future user profile inference.

Actor can represent a human, device, service, system, or Iris itself. One human
may have multiple provider accounts. Linking or merging accounts changes future
resolution, but must not delete memory by default.

## Identity

Identity is a resolved per-observation snapshot of an Actor. It is not a store
and not the durable profile itself.

Identity includes `actor_id`, `actor_kind`, `display_name`, optional provider
info, optional `account_id`, optional `device_id`, and metadata. Resolved
Identity is passed into the cognitive runtime as context.

## Space

Space is the external interaction context, such as a CLI one-shot request, CLI
REPL session, Discord DM, Discord channel, Discord thread, or future voice room.

Space is not the primary owner of user memory. It may narrow memory retrieval as
a context key, but must not store full conversation history or persona state.
Space should remain lightweight.

## SpaceBinding

SpaceBinding maps `provider + provider_space_ref` to a stable Iris-internal
`space_id`. A binding may be persisted.

SpaceBinding may store provider, provider space ref, internal space ID, display
name, space kind, and small metadata.

SpaceBinding must not store conversation history, long-term personality state,
user memory body, or relationship state.
