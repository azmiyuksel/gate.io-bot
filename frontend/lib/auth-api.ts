// Auth client: talks to the backend /auth endpoints and persists tokens in
// localStorage so a session survives page reloads. Access tokens are short-lived;
// refresh() rotates them using the long-lived (revocable) refresh token.

const apiUrl = "/api/v1";

const ACCESS_KEY = "gatebot.access_token";
const REFRESH_KEY = "gatebot.refresh_token";

export interface TokenPair {
  access_token: string;
  refresh_token: string;
}

export function getAccessToken(): string {
  if (typeof window === "undefined") return "";
  return window.localStorage.getItem(ACCESS_KEY) ?? "";
}

export function getRefreshToken(): string {
  if (typeof window === "undefined") return "";
  return window.localStorage.getItem(REFRESH_KEY) ?? "";
}

export function storeTokens(tokens: TokenPair): void {
  window.localStorage.setItem(ACCESS_KEY, tokens.access_token);
  window.localStorage.setItem(REFRESH_KEY, tokens.refresh_token);
}

export function clearTokens(): void {
  window.localStorage.removeItem(ACCESS_KEY);
  window.localStorage.removeItem(REFRESH_KEY);
}

export async function login(email: string, password: string): Promise<TokenPair> {
  const res = await fetch(`${apiUrl}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) {
    const detail = res.status === 429 ? "Too many attempts" : "Invalid credentials";
    throw new Error(detail);
  }
  const tokens: TokenPair = await res.json();
  storeTokens(tokens);
  return tokens;
}

export async function register(email: string, password: string): Promise<TokenPair> {
  const res = await fetch(`${apiUrl}/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) {
    if (res.status === 409) throw new Error("Email already registered");
    if (res.status === 422) {
      const data = await res.json();
      const msg = data.detail?.[0]?.msg ?? data.detail ?? "Validation error";
      throw new Error(String(msg));
    }
    throw new Error("Registration failed");
  }
  const tokens: TokenPair = await res.json();
  storeTokens(tokens);
  return tokens;
}

export async function refreshAccessToken(): Promise<string | null> {
  const refresh_token = getRefreshToken();
  if (!refresh_token) return null;
  const res = await fetch(`${apiUrl}/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token }),
  });
  if (!res.ok) {
    clearTokens();
    return null;
  }
  const tokens: TokenPair = await res.json();
  storeTokens(tokens);
  return tokens.access_token;
}

export async function logout(): Promise<void> {
  const refresh_token = getRefreshToken();
  if (refresh_token) {
    try {
      await fetch(`${apiUrl}/auth/logout`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token }),
      });
    } catch {
      // Best-effort: clear local state regardless.
    }
  }
  clearTokens();
}

// Fetch wrapper that transparently refreshes the access token once on 401.
export async function authFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const access = getAccessToken();
  const withAuth = (tok: string): RequestInit => ({
    ...init,
    headers: { ...(init.headers ?? {}), Authorization: `Bearer ${tok}` },
  });

  let res = await fetch(`${apiUrl}${path}`, withAuth(access));
  if (res.status === 401) {
    const refreshed = await refreshAccessToken();
    if (refreshed) res = await fetch(`${apiUrl}${path}`, withAuth(refreshed));
  }
  return res;
}
