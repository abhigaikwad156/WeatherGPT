import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach } from "vitest";

import { App } from "./App";
import { ACCESS_TOKEN_STORAGE_KEY, clearAuthenticatedSession } from "./auth/session";

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
});

test("renders the login screen", () => {
  render(<MemoryRouter initialEntries={["/login"]}><App /></MemoryRouter>);
  expect(screen.getByRole("heading", { name: "Sign in to your account" })).toBeInTheDocument();
});

test("opens the login screen from the development server root", () => {
  render(<MemoryRouter initialEntries={["/"]}><App /></MemoryRouter>);
  expect(screen.getByRole("heading", { name: "Sign in to your account" })).toBeInTheDocument();
});

test("does not load the dashboard without an access token", () => {
  render(<MemoryRouter initialEntries={["/dashboard"]}><App /></MemoryRouter>);
  expect(screen.getByRole("heading", { name: "Sign in to your account" })).toBeInTheDocument();
});

test("still blocks a protected URL after logout and a browser refresh", () => {
  localStorage.setItem(ACCESS_TOKEN_STORAGE_KEY, "access-token");
  clearAuthenticatedSession();

  render(<MemoryRouter initialEntries={["/dashboard"]}><App /></MemoryRouter>);

  expect(screen.getByRole("heading", { name: "Sign in to your account" })).toBeInTheDocument();
});
