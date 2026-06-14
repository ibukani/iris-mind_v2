# ADR 0002: Runtime State Persistence Policy

## Status

Accepted

## Context

Iris Runtime supports two state backends:

- memory
- sqlite

The backend controls durable companion state, not every runtime cache.

## Decision

When `state.backend = "memory"`, all runtime state is process-local.

When `state.backend = "sqlite"`, Iris persists:

- account bindings
- actor identity links
- long-term memory records
- activity journal records

Iris keeps these process-local even with SQLite backend:

- activity projections
- presence
- space occupancy
- ephemeral space bindings

Relationship baseline and affect / mood baseline are durable targets, but remain deferred until dedicated stores exist.

## Activity Journal

Activity journal is durable when `state.backend = "sqlite"`.

It is an append-only audit log for investigation, debugging, provider event deduplication, future replay, and future projection rebuild.

It is not a hot query path for normal runtime processing.

Normal runtime context should use projections and current-state stores instead of scanning the journal.

## Rationale

Actor identity owns long-term memory and relationship semantics.

Space is contextual scope, not the primary owner of memory.

Presence and occupancy are current-state signals and must not survive process restart.

Activity journal is historical evidence and should survive restart.

## Consequences

`state.backend = "sqlite"` does not mean every runtime store is SQLite.

It means durable companion state and audit history use SQLite while volatile runtime state remains in-memory.
