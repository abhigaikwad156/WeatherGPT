import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";

import { WeatherCard } from "./dataCards";

test("renders OpenWeather metrics supplied by the API", () => {
  render(<WeatherCard weather={{
    temperatureCelsius: 24,
    condition: "light rain",
    rainfallMm: 1.2,
    humidityPercent: 65,
    windSpeedKph: 18,
    pressureHpa: 1012,
    observedAt: "2026-01-01T00:00:00Z"
  }} />);

  expect(screen.getByText("65 %")).toBeInTheDocument();
  expect(screen.getByText("18 km/h")).toBeInTheDocument();
  expect(screen.getByText("1012 hPa")).toBeInTheDocument();
});

test("does not substitute values when weather metrics are unavailable", () => {
  render(<WeatherCard weather={{
    temperatureCelsius: null,
    condition: null,
    rainfallMm: null,
    humidityPercent: null,
    windSpeedKph: null,
    pressureHpa: null,
    observedAt: null
  }} />);

  expect(screen.getByText("Weather condition not available")).toBeInTheDocument();
  expect(screen.getAllByText("—")).toHaveLength(5);
});
