# Boundary Rules

This file defines the boundaries that AI coding agents most often damage.

## External input boundary

All external app events must become typed observations before cognitive code sees them.

Examples:

- `ActorMessageObservation`
- `IdleTickObservation`
- `ActivityEventObservation`
- `PresenceSignalObservation`

Do not pass Discord, Twitch, voice, HTTP, or CLI objects into `cognitive/`.

`ActorMessageObservation` is the only actor text-message ingress.
Actor-scoped activity and all presence signals require a resolved actor/account subject.
Activity and presence observations are external claims, not commands that mutate runtime state.

## Cognitive boundary

`cognitive/` reads typed contracts and produces an `ActionPlan`. It must not know how an external app sends, speaks, displays, or schedules an action.

Allowed cognitive output:

```text
ActionPlan
```

Forbidden cognitive output:

```text
Discord message send
Voice synthesis command
OpenAI provider payload
Raw app command string
```

## Presentation boundary

Presentation converts `ActionPlan` into `PresentedOutput`.

Presentation may decide text shape, style hints, emotion hints, expression hints, and timing hints. It must not execute external actions.

## Safety boundary

Safety checks are explicit gates:

```text
ActionPlan → ActionSafetyGate → Presenter → PresentedOutput → OutputSafetyGate
```

Safety must not be hidden inside LLM prompt construction or adapter code.

## App action boundary

External app actions are app-specific commands. They belong outside cognitive logic.

Examples:

- `SendMessageAction`
- `SpeakAction`
- `ToolCallAction`

## Learning boundary

Learning happens after `ActionResult`, because the runtime needs to know whether the action was sent, blocked, cancelled, or failed.

Do not update durable memory only because an `ActionPlan` was proposed.

## Proactive boundary

Proactive behavior starts from an internal observation, normally `IdleTickObservation`.

Required path:

```text
Scheduler
→ IdleTickObservation
→ CognitiveCycle
→ ActionPlan
→ normal safety/presentation/output path
```

Forbidden path:

```text
Scheduler
→ direct LLM call
→ direct app send
```

## no-action boundary

Canonical no-action plan:

```python
ActionPlan(turn_intent="no_action", candidate_text=None, should_respond=False)
```

No-action means:

- do not call the LLM for response generation
- do not generate actor-visible text
- do not call presenter as if it were a real response
- do not call external app execution
- return or preserve `PresentedOutput(text=None)` at runtime boundary

## Scheduler / delivery boundary

Required path:

```text
RuntimeScheduler
→ typed internal Observation
→ IrisRuntimeService
→ normal CognitiveCycle
→ ActionSafetyGate
→ Presenter
→ OutputSafetyGate
→ DeliverySafetyGate
→ DeliveryOutbox
→ external client polling
→ ActionResult
```

Scheduler emits typed observations only. Proactive talk starts from `IdleTickObservation`.

Delivery is an outbox boundary, not a sender. External clients poll actions and report `ActionResult`. `ReportActionResult` must be idempotent. `NoAction` is not delivered.

Forbidden:

```text
Scheduler → direct LLM call → direct external send
Scheduler → Discord / CLI / voice SDK
features/proactive_talk → runtime.delivery / runtime.scheduler / safety
```
