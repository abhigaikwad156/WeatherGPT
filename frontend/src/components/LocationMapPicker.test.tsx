import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { weatherGptApi } from "../api/weatherGpt";
import { LocationMapPicker, type FarmLocationSelection } from "./LocationMapPicker";

const mapState = vi.hoisted(() => ({
  click: undefined as
    | ((event: { latlng: { lat: number; lng: number } }) => void)
    | undefined,
  map: { flyTo: vi.fn(), getZoom: () => 5 }
}));

vi.mock("react-leaflet", async () => {
  const React = await import("react");
  return {
    MapContainer: ({ children }: { children: ReactNode }) =>
      React.createElement(
        "div",
        { "data-testid": "map" },
        React.createElement(
          "button",
          {
            type: "button",
            onClick: () =>
              mapState.click?.({ latlng: { lat: 18.5204, lng: 73.8567 } })
          },
          "Select map point"
        ),
        children
      ),
    Marker: ({ position }: { position: [number, number] }) =>
      React.createElement("span", { "data-testid": "map-marker" }, position.join(",")),
    TileLayer: () => null,
    useMapEvents: (handlers: {
      click: (event: { latlng: { lat: number; lng: number } }) => void;
    }) => {
      mapState.click = handlers.click;
      return mapState.map;
    }
  };
});

vi.mock("../api/weatherGpt", () => ({
  weatherGptApi: {
    searchLocations: vi.fn(),
    reverseGeocodeLocation: vi.fn()
  }
}));

vi.mock("./LocationConsent", () => ({
  LocationConsent: () => <p>Use my current location (optional)</p>
}));

function renderPicker(props: {
  onConfirm?: (selection: FarmLocationSelection) => void;
  onCancel?: () => void;
} = {}) {
  return render(
    <LocationMapPicker
      onConfirm={props.onConfirm ?? vi.fn()}
      onCancel={props.onCancel ?? vi.fn()}
    />
  );
}

beforeEach(() => {
  mapState.click = undefined;
  vi.mocked(weatherGptApi.searchLocations).mockReset();
  vi.mocked(weatherGptApi.reverseGeocodeLocation).mockReset();
});

afterEach(() => vi.restoreAllMocks());

test("selects map coordinates and confirms them without GPS", () => {
  const onConfirm = vi.fn();
  renderPicker({ onConfirm });

  fireEvent.click(screen.getByRole("button", { name: "Select map point" }));

  expect(screen.getByText("Latitude: 18.520400")).toBeInTheDocument();
  expect(screen.getByText("Longitude: 73.856700")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Confirm selected location" }));
  expect(onConfirm).toHaveBeenCalledWith({
    latitude: 18.5204,
    longitude: 73.8567,
    location_name: null
  });
});

test("uses search coordinates and the returned locality name", async () => {
  vi.mocked(weatherGptApi.searchLocations).mockResolvedValue([
    {
      latitude: "18.5204",
      longitude: "73.8567",
      location_name: "Pune, Maharashtra",
      city: "Pune",
      district: "Pune District"
    }
  ]);
  const onConfirm = vi.fn();
  renderPicker({ onConfirm });

  fireEvent.change(screen.getByRole("searchbox", { name: /search village/i }), {
    target: { value: "Pune" }
  });
  fireEvent.click(screen.getByRole("button", { name: "Search" }));
  fireEvent.click(await screen.findByRole("button", { name: /Pune, Maharashtra/ }));
  fireEvent.click(screen.getByRole("button", { name: "Confirm selected location" }));

  expect(weatherGptApi.searchLocations).toHaveBeenCalledWith("Pune");
  expect(onConfirm).toHaveBeenCalledWith({
    latitude: 18.5204,
    longitude: 73.8567,
    location_name: "Pune, Maharashtra"
  });
});

test("keeps selected coordinates when reverse geocoding fails", async () => {
  vi.mocked(weatherGptApi.reverseGeocodeLocation).mockRejectedValue(new Error("provider unavailable"));
  const onConfirm = vi.fn();
  renderPicker({ onConfirm });
  fireEvent.click(screen.getByRole("button", { name: "Select map point" }));
  fireEvent.click(screen.getByRole("button", { name: "Find nearby place" }));

  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Place details could not be resolved. The selected coordinates are unchanged."
  );
  fireEvent.click(screen.getByRole("button", { name: "Confirm selected location" }));

  expect(onConfirm).toHaveBeenCalledWith({
    latitude: 18.5204,
    longitude: 73.8567,
    location_name: null
  });
});

test("keeps manual map selection available when place search fails", async () => {
  vi.mocked(weatherGptApi.searchLocations).mockRejectedValue(new Error("provider unavailable"));
  renderPicker();
  fireEvent.change(screen.getByRole("searchbox", { name: /search village/i }), {
    target: { value: "Pune" }
  });
  fireEvent.click(screen.getByRole("button", { name: "Search" }));

  expect(await screen.findByRole("alert")).toHaveTextContent(/search is temporarily unavailable/i);
  fireEvent.click(screen.getByRole("button", { name: "Select map point" }));
  expect(screen.getByText("Latitude: 18.520400")).toBeInTheDocument();
});

test("rejects invalid search coordinates without confirming them", async () => {
  vi.mocked(weatherGptApi.searchLocations).mockResolvedValue([
    {
      latitude: "91",
      longitude: "73.8567",
      location_name: "Invalid result",
      city: null,
      district: null
    }
  ]);
  const onConfirm = vi.fn();
  renderPicker({ onConfirm });
  fireEvent.change(screen.getByRole("searchbox", { name: /search village/i }), {
    target: { value: "Invalid" }
  });
  fireEvent.click(screen.getByRole("button", { name: "Search" }));
  fireEvent.click(await screen.findByRole("button", { name: /Invalid result/ }));

  await waitFor(() =>
    expect(screen.getByRole("alert")).toHaveTextContent(/invalid coordinates/i)
  );
  expect(screen.queryByText("Latitude: 91.000000")).not.toBeInTheDocument();
  expect(onConfirm).not.toHaveBeenCalled();
});

test("cancel leaves the selection uncommitted", () => {
  const onConfirm = vi.fn();
  const onCancel = vi.fn();
  renderPicker({ onConfirm, onCancel });
  fireEvent.click(screen.getByRole("button", { name: "Select map point" }));
  fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

  expect(onCancel).toHaveBeenCalledOnce();
  expect(onConfirm).not.toHaveBeenCalled();
});
