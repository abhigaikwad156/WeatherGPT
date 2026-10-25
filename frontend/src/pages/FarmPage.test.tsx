import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { weatherGptApi } from "../api/weatherGpt";
import { FarmPage } from "./FarmPage";

vi.mock("../api/weatherGpt", () => ({
  weatherGptApi: {
    getFarms: vi.fn(),
    getFarmLocation: vi.fn(),
    getFarmCrops: vi.fn(),
    createFarm: vi.fn(),
    updateFarmLocation: vi.fn()
  }
}));

vi.mock("../components/LocationMapPicker", () => ({
  LocationMapPicker: ({
    onConfirm
  }: {
    onConfirm: (selection: {
      latitude: number;
      longitude: number;
      location_name: string | null;
    }) => void;
  }) => (
    <button
      type="button"
      onClick={() =>
        onConfirm({
          latitude: 18.5204,
          longitude: 73.8567,
          location_name: "Pune, Maharashtra"
        })
      }
    >
      Select test farm location
    </button>
  )
}));

beforeEach(() => {
  vi.mocked(weatherGptApi.getFarms).mockResolvedValue([]);
  vi.mocked(weatherGptApi.createFarm).mockResolvedValue({
    id: "farm-1",
    name: "My farm",
    latitude: 18.5204,
    longitude: 73.8567,
    area_hectares: 2,
    soil_type: null,
    irrigation_type: null,
    soil_moisture_percent: null
  });
});

afterEach(() => vi.restoreAllMocks());

test("saves only the confirmed map coordinates and resolved location name", async () => {
  render(<FarmPage />);

  fireEvent.click(await screen.findByRole("button", { name: "Select test farm location" }));
  fireEvent.change(screen.getByRole("textbox", { name: "Farm name" }), {
    target: { value: "My farm" }
  });
  fireEvent.change(screen.getByRole("spinbutton", { name: "Area (hectares)" }), {
    target: { value: "2" }
  });
  fireEvent.click(screen.getByRole("button", { name: "Save farm" }));

  await waitFor(() =>
    expect(weatherGptApi.createFarm).toHaveBeenCalledWith({
      name: "My farm",
      latitude: 18.5204,
      longitude: 73.8567,
      location_name: "Pune, Maharashtra",
      area_hectares: 2,
      soil_type: undefined,
      irrigation_type: undefined,
      soil_moisture_percent: undefined
    })
  );
  expect(weatherGptApi.getFarms).toHaveBeenCalledTimes(2);
});
