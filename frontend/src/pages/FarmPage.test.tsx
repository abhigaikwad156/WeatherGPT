import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { weatherGptApi } from "../api/weatherGpt";
import { LocationProvider } from "../location/LocationContext";
import { FarmPage } from "./FarmPage";

vi.mock("../api/weatherGpt", () => ({
  weatherGptApi: {
    getFarms: vi.fn(),
    getFarmLocation: vi.fn(),
    getFarmCrops: vi.fn(),
    getCurrentLocation: vi.fn(),
    saveCurrentLocation: vi.fn(),
    useCurrentLocationForFarm: vi.fn(),
    createFarm: vi.fn()
  }
}));

const currentLocation = {
  latitude: "17.000000",
  longitude: "74.000000",
  accuracy_meters: "25.00",
  updated_at: "2026-09-18T00:00:00Z",
  location_name: "Current location",
  city: "Current location",
  district: null,
  state: "Maharashtra",
  country: "India",
  country_code: "IN"
};

beforeEach(() => {
  vi.mocked(weatherGptApi.getFarms).mockResolvedValue([
    { id: "farm-1", name: "My farm", latitude: 18, longitude: 73, area_hectares: 2, soil_type: "Loamy", irrigation_type: "Drip", soil_moisture_percent: null }
  ]);
  vi.mocked(weatherGptApi.getFarmLocation).mockResolvedValue({
    latitude: 18,
    longitude: 73,
    accuracy_meters: null,
    location_name: "Farm location",
    created_at: "2026-09-18T00:00:00Z",
    updated_at: "2026-09-18T00:00:00Z"
  });
  vi.mocked(weatherGptApi.getFarmCrops).mockResolvedValue([]);
  vi.mocked(weatherGptApi.getCurrentLocation).mockResolvedValue(currentLocation);
  vi.mocked(weatherGptApi.saveCurrentLocation).mockResolvedValue(currentLocation);
  vi.mocked(weatherGptApi.useCurrentLocationForFarm).mockResolvedValue({
    latitude: 17,
    longitude: 74,
    accuracy_meters: 25,
    location_name: null,
    created_at: "2026-09-18T00:00:00Z",
    updated_at: "2026-09-18T00:00:00Z"
  });
});

afterEach(() => {
  vi.restoreAllMocks();
  Object.defineProperty(navigator, "geolocation", { configurable: true, value: undefined });
});

test("keeps the farm location separate and confirms an explicit current-location choice", async () => {
  const position = { coords: { latitude: 17, longitude: 74, accuracy: 25 } } as GeolocationPosition;
  Object.defineProperty(navigator, "geolocation", {
    configurable: true,
    value: { getCurrentPosition: vi.fn((resolve: PositionCallback) => resolve(position)) }
  });

  render(<LocationProvider><FarmPage /></LocationProvider>);
  expect(await screen.findByText("Farm location")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Edit farm location" }));
  fireEvent.click(screen.getAllByRole("button", { name: /use my current location/i })[0]);
  fireEvent.click(screen.getByRole("button", { name: "Allow location" }));
  fireEvent.click(await screen.findByRole("button", { name: "Confirm farm" }));

  await waitFor(() => expect(weatherGptApi.useCurrentLocationForFarm).toHaveBeenCalledWith("farm-1"));
});
