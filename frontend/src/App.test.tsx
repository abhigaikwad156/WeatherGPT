import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { App } from "./App";

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
