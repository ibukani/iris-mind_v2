# Cognitive Cycle Rules

`CognitiveCycle` is a pipeline coordinator. It is not a God Service.

## Required pattern

```python
for step in self._steps:
    result = await step.run(frame)
    frame = self._frame_builder.apply(frame, result)
```

Each step receives a read-only frame snapshot and returns a typed result.

## Forbidden pattern

```python
memory = await self.memory.search(user_text)
mood = self.relationship.update(memory)
reply = await self.llm.chat(memory, mood, user_text)
await self.discord.send(reply)
```

This mixes memory, affect, LLM, presentation, and external app execution in one place.

## PipelineStep rules

A `PipelineStep` must:

- accept `WorkspaceFrame`
- return a `PipelineStepResult` subclass
- avoid direct mutation of `WorkspaceFrame`
- avoid calling other pipeline steps directly
- avoid provider/client SDK calls unless the injected port is explicitly part of that step responsibility

A `PipelineStep` must not:

- return an untyped `dict`
- write to frame attributes
- access global runtime state
- call safety gates
- execute app actions

## FrameBuilder rules

`FrameBuilder` is the integration point for step results.

Required:

```python
return replace(frame, field_name=value)
```

Forbidden:

```python
frame.state["x"] = value
frame.services["memory"] = store
```

## WorkspaceFrame rules

`WorkspaceFrame` is a typed one-turn snapshot.

Allowed contents:

- observation
- interpreted input
- identity context
- conversation context
- retrieved memory summary
- affect state
- relationship snapshot
- motivation state
- goals
- constraints
- candidate actions

Forbidden contents:

- stores
- adapters
- service managers
- full raw logs
- global configuration objects
- `dict[str, Any]` or `dict[str, object]` at internal boundaries
- raw provider request payloads

## Action selection rules

Action selection produces an app-agnostic `ActionPlan`.

It may choose:

- text response
- no action
- proactive talk intent
- tool/action candidates if represented by typed contracts

It must not:

- send the response
- format for a specific platform
- bypass safety gates
- update durable state as if the action succeeded
