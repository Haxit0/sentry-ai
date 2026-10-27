const baseUrl = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

export async function request<T>(
  path: string,
  options: RequestInit = {},
  timeoutMs = 15_000,
): Promise<T> {
  const controller = new AbortController();
  const abort = () => controller.abort();
  options.signal?.addEventListener("abort", abort, { once: true });
  if (options.signal?.aborted) controller.abort();
  const timeout = window.setTimeout(abort, timeoutMs);
  try {
    const response = await fetch(`${baseUrl}${path}`, {
      ...options,
      headers: { Accept: "application/json", ...options.headers },
      signal: controller.signal,
    });
    if (!response.ok) {
      let message = `The API returned HTTP ${response.status}.`;
      try {
        const body: { detail?: unknown } = await response.json();
        if (typeof body.detail === "string") message = body.detail;
        if (Array.isArray(body.detail))
          message = "The scenario was rejected. Check the supplier and delay.";
      } catch {
        /* Keep the HTTP status when an upstream response is not JSON. */
      }
      throw new Error(message);
    }
    return (await response.json()) as T;
  } catch (error) {
    if (controller.signal.aborted && !options.signal?.aborted) {
      throw new Error(
        "The API took too long to respond. Check that the backend is running on port 8000.",
      );
    }
    if (error instanceof TypeError) {
      throw new Error(
        "Cannot reach the API. Start the backend on port 8000, then try again.",
      );
    }
    throw error;
  } finally {
    window.clearTimeout(timeout);
    options.signal?.removeEventListener("abort", abort);
  }
}
