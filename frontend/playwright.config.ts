import { defineConfig } from "@playwright/test";
import { fileURLToPath } from "node:url";

// WSL uses the POSIX venv layout; native Windows uses Scripts/python.exe.
const python = fileURLToPath(
  new URL(
    process.platform === "win32"
      ? "../.venv/Scripts/python.exe"
      : "../.venv/bin/python",
    import.meta.url,
  ),
);
// Playwright runs webServer commands through the platform shell. Quote the
// absolute executable path so checkouts with spaces work on every platform.
const pythonCommand =
  process.platform === "win32"
    ? `"${python}"`
    : `'${python.replace(/'/g, "'\\''")}'`;

export default defineConfig({
  testDir: "./tests",
  fullyParallel: true,
  workers: 2,
  use: {
    baseURL: "http://127.0.0.1:5173",
    browserName: "chromium",
    launchOptions: {
      executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH,
    },
    trace: "retain-on-failure",
  },
  webServer: [
    {
      command: `${pythonCommand} -m uvicorn app.main:app --host 127.0.0.1 --port 8000`,
      cwd: fileURLToPath(new URL("../backend", import.meta.url)),
      url: "http://127.0.0.1:8000/api/health",
      reuseExistingServer: !process.env.CI,
    },
    {
      command: "npm run dev",
      url: "http://127.0.0.1:5173",
      reuseExistingServer: !process.env.CI,
    },
  ],
});
