import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";

import { ApiError } from "../api/client";
import { weatherGptApi } from "../api/weatherGpt";
import { AlertsPage, RecommendationsPage, ResourcePage } from "./FeaturePages";

vi.mock("../api/weatherGpt", () => ({
  weatherGptApi: {
    getAlerts: vi.fn(),
    getRecommendations: vi.fn(),
    getProfile: vi.fn(),
    updateProfile: vi.fn()
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

test("shows a loading state while recommendations are fetched", () => {
  vi.mocked(weatherGptApi.getRecommendations).mockReturnValue(new Promise(() => {}));

  render(<RecommendationsPage />);

  expect(screen.getByRole("status")).toHaveTextContent("Loading");
});

test("shows deterministic decisions and evidence", async () => {
  vi.mocked(weatherGptApi.getRecommendations).mockResolvedValue({
    status: "available",
    message: null,
    farms: [{
      farmId: "farm-1",
      farmName: "North field",
      weatherProvider: "Open-Meteo",
      weatherFetchedAt: "2026-05-20T10:00:00Z",
      status: "available",
      recommendations: [{
        id: "farm-1:crop-1:extreme_weather",
        recommendationType: "extreme_weather",
        cropId: "crop-1",
        cropName: "Wheat",
        decision: "HIGH_RISK",
        riskLevel: "HIGH",
        confidence: 0.9,
        status: "available",
        reasons: ["The trusted forecast contains a severe-weather signal"]
      }]
    }]
  });

  render(<RecommendationsPage />);

  expect(await screen.findByRole("heading", { name: "North field" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "HIGH_RISK" })).toBeInTheDocument();
  expect(screen.getByText("The trusted forecast contains a severe-weather signal")).toBeInTheDocument();
});

test("shows missing-input details when no rule can produce a decision", async () => {
  vi.mocked(weatherGptApi.getRecommendations).mockResolvedValue({
    status: "insufficient_data",
    message: "No rule-based decision is available yet.",
    farms: [{
      farmId: "farm-1",
      farmName: "North field",
      weatherProvider: "Open-Meteo",
      weatherFetchedAt: "2026-05-20T10:00:00Z",
      status: "insufficient_data",
      recommendations: [{
        id: "farm-1:farm:irrigation",
        recommendationType: "irrigation",
        cropId: null,
        cropName: null,
        decision: "NEEDS_INPUT",
        riskLevel: "UNKNOWN",
        confidence: 0,
        status: "needs_input",
        reasons: ["No matching crop-specific irrigation profile is configured"]
      }]
    }]
  });

  render(<RecommendationsPage />);

  expect(await screen.findByText("No rule-based decision is available yet.")).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Additional inputs required" })).toBeInTheDocument();
  expect(screen.getByText("No matching crop-specific irrigation profile is configured")).toBeInTheDocument();
});

test("shows an actionable empty state when the user has no farm", async () => {
  vi.mocked(weatherGptApi.getRecommendations).mockResolvedValue({
    status: "insufficient_data",
    message: "Add a farm with its location before requesting recommendations.",
    farms: []
  });

  render(<RecommendationsPage />);

  expect(await screen.findByText(
    "Add a farm with its location before requesting recommendations."
  )).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Add a farm" })).toHaveAttribute("href", "/farms");
});

test("shows an error state when recommendations cannot be loaded", async () => {
  vi.mocked(weatherGptApi.getRecommendations).mockRejectedValue(
    new Error("Current farm weather is unavailable")
  );

  render(<RecommendationsPage />);

  expect(await screen.findByRole("alert")).toHaveTextContent("Current farm weather is unavailable");
});

const savedProfile = {
  id: "user-1",
  email: "farmer@example.com",
  display_name: "Asha Farmer",
  preferred_language: "mr",
  location: "Pune",
  preferred_units: "metric"
};

test("shows a loading state while the profile is fetched", () => {
  vi.mocked(weatherGptApi.getProfile).mockReturnValue(new Promise(() => {}));

  render(<ResourcePage resource="profile" />);

  expect(screen.getByRole("status")).toHaveTextContent("Loading your profile");
});

test("loads profile fields and preselects saved preferences", async () => {
  vi.mocked(weatherGptApi.getProfile).mockResolvedValue(savedProfile);

  render(<ResourcePage resource="profile" />);

  expect(await screen.findByRole("heading", { name: "Asha Farmer" })).toBeInTheDocument();
  expect(screen.getByText("farmer@example.com")).toBeInTheDocument();
  expect(screen.getByText("Pune")).toBeInTheDocument();
  expect(screen.getByLabelText("Preferred language")).toHaveValue("mr");
  expect(screen.getByLabelText("Preferred units")).toHaveValue("metric");
});

test("saves edited preferences and only confirms after the API succeeds", async () => {
  vi.mocked(weatherGptApi.getProfile).mockResolvedValue(savedProfile);
  let completeSave: (profile: typeof savedProfile) => void = () => {};
  vi.mocked(weatherGptApi.updateProfile).mockReturnValue(new Promise((resolve) => {
    completeSave = resolve;
  }));

  render(<ResourcePage resource="profile" />);

  fireEvent.change(await screen.findByLabelText("Preferred language"), {
    target: { value: "hi" }
  });
  fireEvent.change(screen.getByLabelText("Preferred units"), {
    target: { value: "imperial" }
  });
  fireEvent.click(screen.getByRole("button", { name: "Save preferences" }));

  expect(weatherGptApi.updateProfile).toHaveBeenCalledWith({
    preferred_language: "hi",
    preferred_units: "imperial"
  });
  expect(screen.getByRole("button", { name: "Saving…" })).toBeDisabled();
  expect(screen.queryByText("Your preferences were saved.")).not.toBeInTheDocument();

  completeSave({ ...savedProfile, preferred_language: "hi", preferred_units: "imperial" });

  expect(await screen.findByRole("status")).toHaveTextContent("Your preferences were saved.");
  expect(screen.getByLabelText("Preferred language")).toHaveValue("hi");
  expect(screen.getByLabelText("Preferred units")).toHaveValue("imperial");
});

test("shows validation and API errors when saving fails", async () => {
  vi.mocked(weatherGptApi.getProfile).mockResolvedValue(savedProfile);
  vi.mocked(weatherGptApi.updateProfile).mockRejectedValue(
    new ApiError("Request validation failed", 422)
  );

  render(<ResourcePage resource="profile" />);
  fireEvent.click(await screen.findByRole("button", { name: "Save preferences" }));

  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Please check your selected preferences. Request validation failed"
  );
  expect(screen.queryByText("Your preferences were saved.")).not.toBeInTheDocument();

  vi.mocked(weatherGptApi.updateProfile).mockRejectedValue(new Error("Service unavailable"));
  fireEvent.click(screen.getByRole("button", { name: "Save preferences" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("Service unavailable");
});

test("handles missing optional location and retries a failed profile request", async () => {
  vi.mocked(weatherGptApi.getProfile)
    .mockRejectedValueOnce(new Error("Profile unavailable"))
    .mockResolvedValueOnce({ ...savedProfile, location: null });

  render(<ResourcePage resource="profile" />);

  expect(await screen.findByRole("alert")).toHaveTextContent("Profile unavailable");
  fireEvent.click(screen.getByRole("button", { name: "Try again" }));

  expect(await screen.findByText("Not provided")).toBeInTheDocument();
  expect(screen.getByLabelText("Preferred language")).toHaveValue("mr");
  expect(screen.getByLabelText("Preferred units")).toHaveValue("metric");
});
