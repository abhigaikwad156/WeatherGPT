import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { expect, test, vi } from "vitest";

import { weatherGptApi } from "../api/weatherGpt";
import { LocationProvider } from "../location/LocationContext";
import { AppShell } from "./AppShell";

vi.mock("../api/weatherGpt", () => ({
  weatherGptApi: { getCurrentLocation: vi.fn(), getProfile: vi.fn() }
}));

test("shows the saved human-readable current location in the top bar", async () => {
  vi.mocked(weatherGptApi.getCurrentLocation).mockResolvedValue({
    latitude: "17.000000",
    longitude: "74.000000",
    accuracy_meters: "25.00",
    updated_at: "2026-09-18T00:00:00Z",
    location_name: "Saved current location",
    city: "Saved current location",
    district: null,
    state: "Maharashtra",
    country: "India",
    country_code: "IN"
  });
  vi.mocked(weatherGptApi.getProfile).mockResolvedValue({
    id: "user-b",
    email: "asha@example.com",
    display_name: "Asha Patil",
    preferred_language: "mr"
  });

  render(<MemoryRouter><LocationProvider><AppShell /></LocationProvider></MemoryRouter>);

  expect(await screen.findByText("Saved current location")).toBeInTheDocument();
  expect(await screen.findByText("Asha Patil")).toBeInTheDocument();
  expect(screen.getByText("Asha")).toBeInTheDocument();
  expect(screen.getAllByText("AP")).toHaveLength(2);
  expect(screen.queryByText("Ramesh Kumar")).not.toBeInTheDocument();
  expect(screen.queryByText("17.000000")).not.toBeInTheDocument();
});
