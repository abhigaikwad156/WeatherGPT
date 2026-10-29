export const ACCESS_TOKEN_STORAGE_KEY = "weathergpt_access_token";
export const UNAUTHORIZED_EVENT = "weathergpt:unauthorized";
export const SESSION_CHANGED_EVENT = "weathergpt:session-changed";

type SessionSnapshot = {
  generation: number;
  token: string | null;
};

let sessionGeneration = 0;

function clearUserScopedStorage(storage: Storage) {
  for (let index = storage.length - 1; index >= 0; index -= 1) {
    const key = storage.key(index);
    if (key?.startsWith("weathergpt_")) storage.removeItem(key);
  }
}

function hasUserScopedStorage(storage: Storage) {
  for (let index = 0; index < storage.length; index += 1) {
    if (storage.key(index)?.startsWith("weathergpt_")) return true;
  }
  return false;
}

function notifySessionChanged() {
  sessionGeneration += 1;
  window.dispatchEvent(new Event(SESSION_CHANGED_EVENT));
}

export function storeAccessToken(token: string) {
  // A successful login can replace an existing account without an explicit logout.
  // Clear any app-scoped browser data before making the new token active.
  clearUserScopedStorage(localStorage);
  clearUserScopedStorage(sessionStorage);
  localStorage.setItem(ACCESS_TOKEN_STORAGE_KEY, token);
  notifySessionChanged();
}

export function clearAuthenticatedSession() {
  const hadSessionData = hasUserScopedStorage(localStorage) || hasUserScopedStorage(sessionStorage);
  clearUserScopedStorage(localStorage);
  clearUserScopedStorage(sessionStorage);
  if (hadSessionData) notifySessionChanged();
}

export function getSessionSnapshot(): SessionSnapshot {
  return {
    generation: sessionGeneration,
    token: localStorage.getItem(ACCESS_TOKEN_STORAGE_KEY)
  };
}

export function isCurrentSession(snapshot: SessionSnapshot) {
  return snapshot.generation === sessionGeneration
    && snapshot.token === localStorage.getItem(ACCESS_TOKEN_STORAGE_KEY);
}

function hasExpiredJwt(token: string) {
  try {
    const payload = token.split(".")[1];
    if (!payload) return false;
    const normalized = payload.replace(/-/g, "+").replace(/_/g, "/");
    const decoded = JSON.parse(atob(normalized)) as { exp?: unknown };
    return typeof decoded.exp === "number" && decoded.exp * 1000 <= Date.now();
  } catch {
    // The API remains the authority for malformed or otherwise invalid JWTs.
    return false;
  }
}

export function hasActiveAccessToken() {
  const token = localStorage.getItem(ACCESS_TOKEN_STORAGE_KEY);
  return token !== null && !hasExpiredJwt(token);
}

export class SessionChangedError extends Error {
  constructor() {
    super("Your sign-in session changed. Please retry the request.");
    this.name = "SessionChangedError";
  }
}
