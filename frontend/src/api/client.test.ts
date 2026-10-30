import { beforeEach, expect, test, vi } from "vitest";

import {
  ACCESS_TOKEN_STORAGE_KEY,
  clearAuthenticatedSession,
  SessionChangedError,
  storeAccessToken,
  UNAUTHORIZED_EVENT
} from "../auth/session";
import { request } from "./client";
import { weatherGptApi } from "./weatherGpt";

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
  vi.restoreAllMocks();
});

test("clears an invalid token and raises the existing unauthorized event", async () => {
  storeAccessToken("invalid-token");
  const onUnauthorized = vi.fn();
  window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: "Could not validate credentials" }), { status: 401 })));

  await expect(request("/users/me")).rejects.toMatchObject({ status: 401 });

  expect(localStorage.getItem(ACCESS_TOKEN_STORAGE_KEY)).toBeNull();
  expect(onUnauthorized).toHaveBeenCalledTimes(1);
  window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
});

test("does not return a previous session's response after logout", async () => {
  storeAccessToken("old-user-token");
  let resolveResponse: ((response: Response) => void) | undefined;
  vi.stubGlobal("fetch", vi.fn().mockImplementation(() => new Promise<Response>((resolve) => { resolveResponse = resolve; })));

  const pending = request<{ private_name: string }>("/users/me");
  clearAuthenticatedSession();
  resolveResponse?.(new Response(JSON.stringify({ private_name: "Previous user" }), { status: 200 }));

  await expect(pending).rejects.toBeInstanceOf(SessionChangedError);
});

test("uses the server weather cache for normal farm-weather reads", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({}), { status: 200 })));

  await weatherGptApi.getFarmWeather("farm-id");

  expect(fetch).toHaveBeenCalledWith(
    "/api/v1/farms/farm-id/weather",
    expect.objectContaining({ cache: "no-store" })
  );
});
