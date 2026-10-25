# Shared baseline verification

Executed locally on 25 October 2026 with Python 3.12.14, Node.js 22.12.0 and npm 10.9.0. Dependencies were installed into this repository's `.venv` and `frontend/node_modules`; those generated directories are ignored.

| Check | Result |
| --- | --- |
| Backend `python -m pytest -q` from `backend` | 40 passed |
| Live `GET /api/health` on port 8000 | 200; fixture mode; integration and agent status `not_configured` |
| Live Alpha +5 simulation | Exposure `500.00`; ranked totals `160.00`, `260.00`, `500.00`; expedite recommended |
| Frontend `npm run build` | TypeScript check and production build passed |
| Dashboard against the real API | Supplier loading, Alpha +5, Alpha +0, stale-input notice, order table and recovery ranking verified |
| API unavailable | Stopped only this project's backend; dashboard displayed a request error; backend then restarted |
| Responsive layout | Desktop 1440px and mobile 390px inspected; no page-wide mobile overflow |
| Dependency install audit | npm reported zero vulnerabilities at installation time |

The passing backend run emitted one upstream Starlette deprecation warning about its `httpx` test-client adapter. It did not fail any test. Tests do not call external integrations.

GitHub Actions separately checks Python 3.11/3.12 and the frontend on Linux. Its actual run result must be inspected on GitHub; local results do not establish CI success. Real Zetaris, Nightshift, Meterless Engine, NVIDIA inference and agent execution remain unimplemented. No existing Docker, Zetaris, WSL2 or Nightshift installation was changed.
