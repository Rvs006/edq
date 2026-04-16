# Agent Instructions

This repository uses [CLAUDE.md](./CLAUDE.md) as the single source of truth for AI-agent guidance. All coding agents (Claude Code, GitHub Copilot Workspace, Cursor, Aider, OpenAI Codex, Devin, etc.) should follow the rules and tool guidance in that file.

Key points lifted from `CLAUDE.md`:

- Architecture: Docker Compose stack (frontend + backend + postgres). Electron is a desktop wrapper, not a dev launcher.
- Backend: FastAPI + async SQLAlchemy + PostgreSQL, all routes under `/api/v1/`.
- Frontend: React 19 + Vite + Tailwind + TanStack Query + Radix UI.
- Tests: pytest for backend, Vitest for frontend. No linter configured.
- Env: root `.env` is the single source of config. Do not create `server/backend/.env`.
- Knowledge graph: use the `code-review-graph` MCP tools for structural exploration before falling back to `Grep`/`Read`.

See [CLAUDE.md](./CLAUDE.md) for the full guide.
