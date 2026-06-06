# Rule: Documentation Language

This rule controls language choice for repository documentation, code comments, docstrings, and agent-facing materials.

## Default rule

Human-facing documentation must be written in Japanese by default.

This includes:

- `README.md`
- files under `docs/`
- design notes meant for human readers
- architecture explanations meant for human readers
- implementation explanations and review summaries
- PR descriptions and release notes when written for human readers
- docstrings and explanatory comments when written for human readers

## Code comments and docstrings

New or updated docstrings and explanatory comments are Japanese by default when they describe behavior, intent, rationale, architecture, invariants, limitations, or operational caveats for human readers.

Use Japanese for:

- public module, class, function, and method docstrings
- explanatory comments near non-obvious logic
- comments documenting architecture decisions or safety constraints
- comments added to make future maintenance easier

English is acceptable when the comment or docstring is primarily machine-oriented, tool-oriented, or tightly coupled to external terminology.

Examples:

- generated code comments
- comments copied from external APIs, protocol specs, or quoted error messages
- short mechanical comments that mirror an external API term
- comments inside agent-only prompts or machine-oriented task contracts
- existing English-only blocks where partial translation would reduce consistency

Do not rename identifiers or translate code-level names solely to satisfy this rule.

## Allowed English

English is allowed when the content is primarily machine-oriented or agent-oriented.

Examples:

- coding-agent prompts
- `.agents/` harness rules and workflows
- tool configuration comments
- architecture guard rule names
- machine-readable contracts
- generated code, identifiers, paths, commands, protocol names, and API names

## Mixed-language handling

Use Japanese for the surrounding explanation. Keep exact technical tokens unchanged.

Do not translate:

- code identifiers
- file paths
- command names
- class/function/type names
- protocol field names
- quoted error messages
- external API names

## Documentation update behavior

When updating human-facing docs, prefer Japanese even if surrounding agent instructions are English.

When updating agent-facing docs, English is acceptable, but reports back to the user must remain Japanese according to `AGENTS.md`.

If a document has both human-facing and agent-facing sections, use Japanese for the human-facing sections and English for the agent/task contract sections where precision is more important.

When updating comments or docstrings in code, apply the same human-facing vs. machine-facing distinction above. Keep surrounding style consistent, but prefer Japanese for new explanatory prose.
