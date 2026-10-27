# Frontend checks

From `frontend`, run `npm ci`, `npm run typecheck`, and `npm run build`.

The browser tests exercise the real fixture API and dashboard together. Prepare
the Python environment from the repository root first. On Linux, macOS or WSL:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
```

On native Windows, use PowerShell:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

The Playwright launcher selects `.venv/Scripts/python.exe` on native Windows and
`.venv/bin/python` on Linux, macOS and WSL. It resolves the executable and backend
directory relative to the configuration file and quotes the executable path to
support checkout paths containing spaces. Create the virtual environment on the
platform where tests run; do not share a Windows venv with WSL or vice versa.

Then, from `frontend`:

```bash
npx playwright install chromium
npm run test:e2e
```

Playwright starts the API on 8000 and Vite on strict port 5173, or reuses healthy
development servers outside CI. Use the fixture backend with its unchanged demo
data. No integration credentials are needed. If Chromium is already installed,
skip the browser download and select it explicitly, for example:

```bash
PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium npm run test:e2e
```

The same optional override in PowerShell uses an actual installed browser path:

```powershell
$env:PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH = 'C:\Program Files\Google\Chrome\Application\chrome.exe'
npm run test:e2e
```

Tests cover paired baseline/disrupted requests, supplier and delay changes,
zero-delay and no-impact scenarios, partial failures, retries, loading and stale
results, and narrow-screen layout. Successful simulation responses come from the
backend; network interception only delays responses or injects failures. Financial
results are not mocked. Traces on failure are written to ignored `test-results/`.

The comparison uses a real zero-delay simulation as its baseline. The frozen API
returns completion dates only for affected (late) orders. For baseline orders
absent from that list, the UI displays **on time by the promised date**, without
claiming an exact completion date. Supplier restock dates can be compared exactly
because both simulation responses include them. Existing recovery costs compare
policies within the disrupted scenario; “No action” is distinct from the
zero-delay baseline.

## Frontend calculation boundary for team review

`exposureChange` is strictly a **display-only subtraction of two backend-computed
monetary values**. It subtracts integer pence to avoid rounding artifacts in the
displayed difference. It does not calculate penalties from dates, fees or order
quantities. Penalty models, recovery costs, ranking, tie priority and strategy
selection belong to the backend and must never be recalculated in the frontend.

The plain-English comparison uses returned supplier/delay values, exposure totals
and affected-order counts. It finds the backend's `recommended_strategy` and
displays that option's returned total, action costs and remaining penalties beside
the other returned totals. Equal totals are described as tied; the UI does not
choose a different recommendation. This is deterministic presentation of fixture
responses, not AI investigation or inference. The frozen API contract is unchanged.

## GitHub Actions coverage

The current `.github/workflows/backend-tests.yml` runs backend pytest and frontend typecheck
and production build. It does **not** execute Playwright or `npm run test:e2e`.
The browser test sources are typechecked, but that does not run the tests. Run
the browser suite locally before review; a green Actions run alone does not
establish browser coverage. No CI workflow changes are included here.
