import { beforeEach, expect, test, vi } from "vitest";

import {
  ACCESS_TOKEN_STORAGE_KEY,
  clearAuthenticatedSession,
  getSessionSnapshot,
  hasActiveAccessToken,
  isCurrentSession,
  SESSION_CHANGED_EVENT,
  storeAccessToken
} from "./session";

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
});

test("logout removes the token and WeatherGPT-scoped browser data", () => {
  const changed = vi.fn();
  window.addEventListener(SESSION_CHANGED_EVENT, changed);
  localStorage.setItem("weathergpt_profile_cache", "private profile");
  sessionStorage.setItem("weathergpt_draft", "private draft");
  localStorage.setItem("unrelated_preference", "keep");
  storeAccessToken("access-token");

  clearAuthenticatedSession();

  expect(localStorage.getItem(ACCESS_TOKEN_STORAGE_KEY)).toBeNull();
  expect(localStorage.getItem("weathergpt_profile_cache")).toBeNull();
  expect(sessionStorage.getItem("weathergpt_draft")).toBeNull();
  expect(localStorage.getItem("unrelated_preference")).toBe("keep");
  expect(changed).toHaveBeenCalledTimes(2);
  window.removeEventListener(SESSION_CHANGED_EVENT, changed);
});

test("a session snapshot becomes invalid after logout", () => {
  storeAccessToken("access-token");
  const snapshot = getSessionSnapshot();

  clearAuthenticatedSession();

  expect(isCurrentSession(snapshot)).toBe(false);
});

test("does not reset an unauthenticated page when there is no session to clear", () => {
  const changed = vi.fn();
  window.addEventListener(SESSION_CHANGED_EVENT, changed);

  clearAuthenticatedSession();

  expect(changed).not.toHaveBeenCalled();
  window.removeEventListener(SESSION_CHANGED_EVENT, changed);
});

test("does not treat an expired JWT as an active client session", () => {
  const expiredPayload = btoa(JSON.stringify({ exp: Math.floor(Date.now() / 1000) - 60 }));
  localStorage.setItem(ACCESS_TOKEN_STORAGE_KEY, `header.${expiredPayload}.signature`);

  expect(hasActiveAccessToken()).toBe(false);
});
