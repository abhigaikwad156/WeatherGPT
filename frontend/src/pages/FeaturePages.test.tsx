import { render, screen } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";

import { weatherGptApi } from "../api/weatherGpt";
import { AlertsPage } from "./FeaturePages";

vi.mock("../api/weatherGpt", () => ({
  weatherGptApi: {
    getAlerts: vi.fn()
  }
}));

beforeEach(() => {
  vi.clearAllMocks();
});

test("shows a loading state while alerts are fetched", () => {
  vi.mocked(weatherGptApi.getAlerts).mockReturnValue(new Promise(() => {}));

  render(<AlertsPage />);

  expect(screen.getByRole("status")).toHaveTextContent("Loading");
});

test("shows an empty state when no active alerts are returned", async () => {
  vi.mocked(weatherGptApi.getAlerts).mockResolvedValue([]);

  render(<AlertsPage />);

  expect(await screen.findByText("No active alerts")).toBeInTheDocument();
});

test("shows persisted alerts when returned by the API", async () => {
  vi.mocked(weatherGptApi.getAlerts).mockResolvedValue([{
    id: "alert-1",
    title: "Persisted weather alert",
    body: "Alert details",
    severity: "high",
    startsAt: "2026-10-25T00:00:00Z"
  }]);

  render(<AlertsPage />);

  expect(await screen.findByRole("heading", { name: "Persisted weather alert" })).toBeInTheDocument();
  expect(screen.getByText("Alert details")).toBeInTheDocument();
});

test("shows an error state when the alerts request fails", async () => {
  vi.mocked(weatherGptApi.getAlerts).mockRejectedValue(new Error("Alerts unavailable"));

  render(<AlertsPage />);

  expect(await screen.findByRole("alert")).toHaveTextContent("Alerts unavailable");
});
