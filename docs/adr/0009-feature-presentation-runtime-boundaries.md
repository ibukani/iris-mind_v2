# ADR 0009: Feature, Presentation, and Runtime Boundaries

## Status

Accepted

## Context

As the Iris runtime grows, features (like `event_reaction` and `proactive_talk`) and their integration into the runtime have begun to blur architectural boundaries. Specifically, runtime wiring imports feature internals (e.g., planners, policies, templates), features sometimes return `PresentedOutput`, and the line between feature logic, presentation formatting, and safety checks is becoming indistinct.

To prevent the `features/` layer from becoming a mini app layer and to keep the runtime modular, we need strict boundaries.

## Decision

We enforce the following boundaries:

1.  **features/**: Owns feature-specific policy, planning, scoring, candidate generation, templates, and feature contribution definitions.
    *   Must not import `runtime`, `presentation`, `safety`, or `adapters`.
    *   Must not return `PresentedOutput`.
    *   Should return domain candidates, decisions, or standard cognitive pipeline results.
2.  **presentation/**: Owns conversion from `ActionPlan` or feature-specific candidates into `PresentedOutput`.
    *   Must not import `features`, `runtime`, `safety`, or `adapters`.
    *   Must remain a formatting/conversion boundary.
3.  **runtime/**: Owns orchestration, wiring, lifecycle, route dispatch, scheduler, delivery, observability, and runtime state integration.
    *   May compose all layers.
    *   Runtime wiring must import feature definition modules (e.g., `FeatureDefinition`), not feature internals (like `planner.py`, `policy.py`, `scoring.py`, or `templates.py`).
    *   Should orchestrate but not own feature policy.
    *   Uses explicit composition instead of auto-discovery or global registries.
4.  **cognitive/**: Owns reusable cognitive primitives and the cognitive cycle.
    *   Stays focused on reusable cognitive primitives, not feature-specific application behavior.
5.  **adapters/**: Owns external technology boundaries.
6.  **Safety gates** are executed outside `features/` and outside `presentation/` by the runtime layer.

## Consequences

*   Features must declare their contributions via `FeatureDefinition`.
*   Presentation logic is cleanly separated from feature decision-making.
*   Runtime wiring is decoupled from feature implementation details.
*   The architecture remains testable and modular.
