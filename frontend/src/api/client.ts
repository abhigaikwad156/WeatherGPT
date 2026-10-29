import {
  clearAuthenticatedSession,
  getSessionSnapshot,
  isCurrentSession,
  SessionChangedError,
  UNAUTHORIZED_EVENT
} from "../auth/session";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "/api/v1";

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number
  ) {
    super(message);
  }
}

export async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const session = getSessionSnapshot();
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    cache: options.cache ?? "no-store",
    headers: {
      "Content-Type": "application/json",
      ...(session.token ? { Authorization: `Bearer ${session.token}` } : {}),
      ...options.headers
    }
  });
  if (!isCurrentSession(session)) throw new SessionChangedError();

  if (!response.ok) {
    if (response.status === 401) {
      clearAuthenticatedSession();
      window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
    }
    const body = (await response.json().catch(() => null)) as
      | { error?: { message?: string }; detail?: string | { msg?: string }[] }
      | null;
    const detail = Array.isArray(body?.detail)
      ? body.detail.map((item) => item.msg).filter(Boolean).join(", ")
      : body?.detail;
    throw new ApiError(body?.error?.message ?? detail ?? "The request could not be completed.", response.status);
  }
  const body = await response.json() as T;
  if (!isCurrentSession(session)) throw new SessionChangedError();
  return body;
}
