# Contributing to EDQ

## Development Setup

1. Clone the repository
2. Install Docker Desktop
3. Run `docker compose up --build`

## Code Standards

### Python (Backend)
- Type hints on every function
- Docstrings on classes and public methods
- Use `async def` for all route handlers
- Pydantic schemas for all request/response validation
- Business logic in `services/`, never in routes

### TypeScript (Frontend)
- Functional components only
- React Query for API data fetching
- Tailwind CSS utility classes
- Dark theme throughout

## Commit Messages

Use descriptive commit messages:
- `feat: add nmap parser with XML output handling`
- `fix: correct CSRF token extraction from cookies`
- `docs: update API endpoint documentation`

## Project Structure

- One model per file in `models/`
- One router per resource in `routes/`
- Pydantic schemas in `schemas/`
- Business logic in `services/`
