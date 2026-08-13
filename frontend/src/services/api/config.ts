type RequiredEnvVar = "VITE_API_BASE_URL" | "VITE_WS_BASE_URL";

/** Pure — takes the already-read env value and mode flag as plain
 * arguments rather than reading `import.meta.env` itself, so it's
 * directly unit-testable without mocking Vite's env-injection machinery.
 *
 * There is no separate "frontend auth configuration" to validate —
 * authentication is just HTTP calls (`/auth/login`, `/auth/refresh`,
 * `/ws?token=...`) against `API_BASE_URL`/`WS_BASE_URL` themselves, with
 * no client id/secret or OAuth config of its own. Validating these two
 * URLs *is* validating the frontend's authentication configuration. */
export function validateRequiredUrl(
  key: RequiredEnvVar,
  value: string | undefined,
  isDev: boolean,
  devDefault: string,
  expectedProtocols: string[],
): string {
  if (!value) {
    if (isDev) return devDefault;
    // A production build with no value set: never silently fall back to
    // a localhost URL that either doesn't exist in this deployment or,
    // worse, silently resolves to some unrelated local service — fail
    // loudly at load time instead (Milestone 10 audit finding). See
    // docs/release/PRODUCTION_CONFIGURATION_GUIDE.md's Frontend section.
    throw new Error(
      `Missing required environment variable "${key}". This build was made without it set, so there is no ` +
        `backend to talk to. Set it at build time — see docs/release/PRODUCTION_CONFIGURATION_GUIDE.md's Frontend section.`,
    );
  }

  let parsed: URL;
  try {
    parsed = new URL(value);
  } catch {
    throw new Error(`Invalid "${key}": "${value}" is not a valid URL.`);
  }
  if (!expectedProtocols.includes(parsed.protocol)) {
    throw new Error(
      `Invalid "${key}": "${value}" uses protocol "${parsed.protocol}" — expected one of ${expectedProtocols.join(", ")}.`,
    );
  }

  return value;
}

/** Base URLs — configured via `.env`/`.env.example`, never hardcoded per
 * call site. In dev mode, falls back to the local backend dev server so
 * `npm run dev` works out of the box against
 * `docs/release/DEPLOYMENT_GUIDE.md`'s own default (`API_PORT=8000`). In
 * a production build, an unset or malformed value throws immediately at
 * module load — before the app renders anything — rather than silently
 * shipping a broken deployment. */
export const API_BASE_URL: string = validateRequiredUrl(
  "VITE_API_BASE_URL",
  import.meta.env.VITE_API_BASE_URL,
  import.meta.env.DEV,
  "http://localhost:8000/api/v1",
  ["http:", "https:"],
);

export const WS_BASE_URL: string = validateRequiredUrl(
  "VITE_WS_BASE_URL",
  import.meta.env.VITE_WS_BASE_URL,
  import.meta.env.DEV,
  "ws://localhost:8000/ws",
  ["ws:", "wss:"],
);
