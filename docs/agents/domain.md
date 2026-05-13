# Domain Docs

How the engineering skills should consume this repo's domain documentation when exploring the codebase.

## Layout

This is a single-context repo.

Read these files before exploring when they exist:

- `CONTEXT.md` at the repo root
- `docs/adr/`

If either path does not exist, proceed silently. Do not flag its absence or suggest creating it upfront. Producer skills create those files lazily when terms or decisions actually get resolved.

## Use the glossary's vocabulary

When output names a domain concept in an issue title, refactor proposal, hypothesis, or test name, use the term as defined in `CONTEXT.md`. Do not drift to synonyms the glossary explicitly avoids.

If the concept is not in the glossary yet, either reconsider whether the project already has better language or note the gap for `grill-with-docs`.

## Flag ADR conflicts

If output contradicts an existing ADR, surface it explicitly rather than silently overriding it.
