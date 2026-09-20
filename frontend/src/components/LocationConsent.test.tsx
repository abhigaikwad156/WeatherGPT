import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { ApiError } from "../api/client";
import { weatherGptApi } from "../api/weatherGpt";
import { LocationProvider } from "../location/LocationContext";
import { LocationConsent } from "./LocationConsent";

vi.mock("../api/weatherGpt", () => ({
  weatherGptApi: {
    getCurrentLocation: vi.fn(),
    saveCurrentLocation: vi.fn()
  }
}));

const location = {
  latitude: "17.000000",
  longitude: "74.000000",
  accuracy_meters: "25.00",
  updated_at: "2026-09-18T00:00:00Z",
  location_name: "Provided location",
  city: "Provided location",
  district: null,
  state: "Maharashtra",
  country: "India",
  country_code: "IN"
};

function renderConsent() {
  return render(<LocationProvider><LocationConsent /></LocationProvider>);
}

function mockGeolocation(
  getCurrentPosition: (
    successCallback: PositionCallback,
    errorCallback?: PositionErrorCallback | null,
    options?: PositionOptions
  ) => void
) {
  Object.defineProperty(navigator, "geolocation", {
    configurable: true,
    value: { getCurrentPosition }
  });
}

beforeEach(() => {
  vi.mocked(weatherGptApi.getCurrentLocation).mockRejectedValue(new ApiError("Not found", 404));
  vi.mocked(weatherGptApi.saveCurrentLocation).mockResolvedValue(location);
});

afterEach(() => {
  vi.restoreAllMocks();
  Object.defineProperty(navigator, "geolocation", { configurable: true, value: undefined });
});

test("does not request GPS on initial load", async () => {
  const getCurrentPosition = vi.fn();
  mockGeolocation(getCurrentPosition);

  renderConsent();

  await waitFor(() => expect(weatherGptApi.getCurrentLocation).toHaveBeenCalledOnce());
  expect(getCurrentPosition).not.toHaveBeenCalled();
});

test("detects GPS only after intentional consent and saves it to the backend", async () => {
  const success = {
    coords: { latitude: 17, longitude: 74, accuracy: 25 }
  } as GeolocationPosition;
  const getCurrentPosition = vi.fn((resolve: PositionCallback) => resolve(success));
  mockGeolocation(getCurrentPosition);

  renderConsent();
  fireEvent.click(screen.getByRole("button", { name: /use my current location/i }));
  expect(screen.getByText(/uses your location/i)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Allow location" }));

  await waitFor(() => expect(weatherGptApi.saveCurrentLocation).toHaveBeenCalledWith({
    latitude: 17,
    longitude: 74,
    accuracy_meters: 25
  }, expect.stringMatching(/^location-/)));
  expect(getCurrentPosition).toHaveBeenCalledWith(
    expect.any(Function),
    expect.any(Function),
    { enableHighAccuracy: true, timeout: 10_000, maximumAge: 0 }
  );
  expect(screen.getByText(/location detected/i)).toBeInTheDocument();
});

test("shows a detecting state while waiting for the browser location", () => {
  let resolvePosition: PositionCallback | undefined;
  mockGeolocation((resolve) => {
    resolvePosition = resolve;
  });

  renderConsent();
  fireEvent.click(screen.getByRole("button", { name: /use my current location/i }));
  fireEvent.click(screen.getByRole("button", { name: "Allow location" }));

  expect(screen.getByRole("button", { name: "Getting your location…" })).toBeDisabled();
  expect(resolvePosition).toBeDefined();
});

describe("location failures", () => {
  test.each([
    [1, "Location permission was denied."],
    [2, "Unable to determine your location."],
    [3, "Location detection timed out."]
  ])("shows a friendly browser error for code %s", async (code, message) => {
    const getCurrentPosition = vi.fn(
      (_: PositionCallback, reject?: PositionErrorCallback | null) =>
        reject?.({ code } as GeolocationPositionError)
    );
    mockGeolocation(getCurrentPosition);
    renderConsent();

    fireEvent.click(screen.getByRole("button", { name: /use my current location/i }));
    fireEvent.click(screen.getByRole("button", { name: "Allow location" }));

    expect(await screen.findByText(message)).toBeInTheDocument();
  });

  test("reports when browser geolocation is unsupported", async () => {
    Object.defineProperty(navigator, "geolocation", { configurable: true, value: undefined });
    renderConsent();

    fireEvent.click(screen.getByRole("button", { name: /use my current location/i }));
    fireEvent.click(screen.getByRole("button", { name: "Allow location" }));

    expect(await screen.findByText("Location services are not supported by this browser.")).toBeInTheDocument();
  });

  test("reports a backend save failure without exposing its technical message", async () => {
    const success = { coords: { latitude: 17, longitude: 74, accuracy: 25 } } as GeolocationPosition;
    mockGeolocation(vi.fn((resolve: PositionCallback) => resolve(success)));
    vi.mocked(weatherGptApi.saveCurrentLocation).mockRejectedValue(new ApiError("private error", 500));
    renderConsent();

    fireEvent.click(screen.getByRole("button", { name: /use my current location/i }));
    fireEvent.click(screen.getByRole("button", { name: "Allow location" }));

    expect(await screen.findByText("Location was detected, but we couldn't save it.")).toBeInTheDocument();
    expect(screen.queryByText("private error")).not.toBeInTheDocument();
  });
});
