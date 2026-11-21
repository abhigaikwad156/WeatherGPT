import { render, screen } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";

import { weatherGptApi } from "../api/weatherGpt";
import { DashboardPage } from "./DashboardPage";

vi.mock("../api/weatherGpt", () => ({
  weatherGptApi: {
    getDashboard: vi.fn()
  }
}));

beforeEach(() => {
  vi.clearAllMocks();
});

test("shows the deterministic irrigation decision, missing inputs, and source", async () => {
  vi.mocked(weatherGptApi.getDashboard).mockResolvedValue({
    currentWeather: null,
    forecast: [],
    activeAlerts: [],
    currentCrop: { name: "Sugarcane", growthStage: "tillering" },
    recommendedActions: [{
      id: "farm:crop:irrigation",
      recommendationType: "irrigation",
      status: "needs_input",
      summary: "NEEDS_INPUT: Sugarcane thresholds need agronomist review",
      decisionVersion: "deterministic-rules-v1",
      decision: "NEEDS_INPUT",
      reasons: ["The stage profile has no reviewed numeric thresholds"],
      explanations: {
        en: "NEEDS_INPUT: The profile is not approved.",
        mr: "अधिक माहिती आवश्यक: हा नियम पडताळलेला नाही."
      },
      dataBasis: "insufficient_data",
      weatherLimitations: ["Rainfall forecast is unavailable."],
      applicableCropStage: "tillering",
      cropAgeDays: 100,
      source: {
        publisher: "MPKV Rahuri",
        documentTitle: "Sugarcane irrigation guidance",
        sourceUri: "https://example.org/sugarcane"
      },
      missingInputs: ["reviewed_soil_moisture_threshold"]
    }],
    upcomingRisks: []
  });

  render(<DashboardPage />);

  expect(await screen.findByText(/NEEDS_INPUT: Sugarcane thresholds need agronomist review/))
    .toBeInTheDocument();
  expect(screen.getByText("Applicable crop stage: tillering · 100 days after planting"))
    .toBeInTheDocument();
  expect(screen.getByText("Missing: agronomist-reviewed soil-moisture threshold")).toBeInTheDocument();
  expect(screen.getByText("अधिक माहिती आवश्यक: हा नियम पडताळलेला नाही.")).toBeInTheDocument();
  expect(screen.getByText("Rainfall forecast is unavailable.")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Sugarcane irrigation guidance" }))
    .toHaveAttribute("href", "https://example.org/sugarcane");
  expect(screen.queryByText("No action yet")).not.toBeInTheDocument();
});
