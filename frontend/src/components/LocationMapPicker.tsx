import { useEffect, useState, type FormEvent } from "react";
import L from "leaflet";
import {
  MapContainer,
  Marker,
  TileLayer,
  useMapEvents
} from "react-leaflet";
import "leaflet/dist/leaflet.css";
import markerIconRetinaUrl from "leaflet/dist/images/marker-icon-2x.png";
import markerIconUrl from "leaflet/dist/images/marker-icon.png";
import markerShadowUrl from "leaflet/dist/images/marker-shadow.png";

import type { CurrentLocation, FarmLocation, GeocodedPlace } from "../api/types";
import { weatherGptApi } from "../api/weatherGpt";
import { LocationConsent } from "./LocationConsent";

const farmMarkerIcon = new L.Icon({
  iconRetinaUrl: markerIconRetinaUrl,
  iconUrl: markerIconUrl,
  shadowUrl: markerShadowUrl,
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [1, -34],
  shadowSize: [41, 41]
});

export interface FarmLocationSelection {
  latitude: number;
  longitude: number;
  location_name: string | null;
}

interface LocationMapPickerProps {
  initialLocation?: Pick<FarmLocation, "latitude" | "longitude" | "location_name"> | null;
  onConfirm: (selection: FarmLocationSelection) => void | Promise<void>;
  onCancel: () => void;
  saving?: boolean;
  confirmLabel?: string;
}

function MapInteractions({
  selected,
  onSelect
}: {
  selected: FarmLocationSelection | null;
  onSelect: (selection: FarmLocationSelection) => void;
}) {
  const map = useMapEvents({
    click(event) {
      onSelect({
        latitude: event.latlng.lat,
        longitude: event.latlng.lng,
        location_name: null
      });
    }
  });

  useEffect(() => {
    if (selected) map.flyTo([selected.latitude, selected.longitude], Math.max(map.getZoom(), 12));
  }, [map, selected]);

  return selected ? (
    <Marker position={[selected.latitude, selected.longitude]} icon={farmMarkerIcon} />
  ) : null;
}

function locationFromGps(location: CurrentLocation): FarmLocationSelection {
  return {
    latitude: Number(location.latitude),
    longitude: Number(location.longitude),
    location_name: location.location_name
  };
}

function isValidCoordinatePair(latitude: number, longitude: number): boolean {
  return (
    Number.isFinite(latitude) &&
    Number.isFinite(longitude) &&
    latitude >= -90 &&
    latitude <= 90 &&
    longitude >= -180 &&
    longitude <= 180
  );
}

export function LocationMapPicker({
  initialLocation,
  onConfirm,
  onCancel,
  saving = false,
  confirmLabel = "Confirm selected location"
}: LocationMapPickerProps) {
  const initialLatitude = Number(initialLocation?.latitude);
  const initialLongitude = Number(initialLocation?.longitude);
  const initialCoordinatesAreValid = isValidCoordinatePair(initialLatitude, initialLongitude);
  const [selected, setSelected] = useState<FarmLocationSelection | null>(
    initialLocation && initialCoordinatesAreValid
      ? {
          latitude: initialLatitude,
          longitude: initialLongitude,
          location_name: initialLocation.location_name
        }
      : null
  );
  const [query, setQuery] = useState("");
  const [searchResults, setSearchResults] = useState<GeocodedPlace[]>([]);
  const [searching, setSearching] = useState(false);
  const [resolving, setResolving] = useState(false);
  const [error, setError] = useState<string | null>(
    initialLocation && !initialCoordinatesAreValid
      ? "The saved farm location has invalid coordinates. Select a valid point on the map."
      : null
  );
  const [status, setStatus] = useState<string | null>(null);
  const [mapReady, setMapReady] = useState(false);

  async function searchPlaces(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (query.trim().length < 3) {
      setError("Enter at least 3 characters to search.");
      setSearchResults([]);
      return;
    }
    setSearching(true);
    setError(null);
    setStatus(null);
    try {
      const results = await weatherGptApi.searchLocations(query.trim());
      setSearchResults(results);
      if (!results.length) setStatus("No matching places found. You can still select directly on the map.");
    } catch {
      setSearchResults([]);
      setError("Place search is temporarily unavailable. You can still select directly on the map.");
    } finally {
      setSearching(false);
    }
  }

  async function resolveSelectedPlace() {
    if (!selected) return;
    setResolving(true);
    setError(null);
    setStatus(null);
    try {
      const result = await weatherGptApi.reverseGeocodeLocation(
        selected.latitude,
        selected.longitude
      );
      if (result?.location_name) {
        setSelected({ ...selected, location_name: result.location_name });
        setStatus(
          [result.city, result.district].filter(Boolean).join(" · ") ||
            "Place details resolved."
        );
      } else {
        setStatus("No locality details were returned. The selected coordinates are unchanged.");
      }
    } catch {
      setError("Place details could not be resolved. The selected coordinates are unchanged.");
    } finally {
      setResolving(false);
    }
  }

  function selectSearchResult(place: GeocodedPlace) {
    const latitude = Number(place.latitude);
    const longitude = Number(place.longitude);
    if (!isValidCoordinatePair(latitude, longitude)) {
      setError("The place search returned invalid coordinates. Choose a location on the map instead.");
      return;
    }
    setSelected({
      latitude,
      longitude,
      location_name: place.location_name
    });
    setSearchResults([]);
    setError(null);
    setStatus(`${place.location_name} selected.`);
  }

  return (
    <section className="farm-location-picker" aria-label="Choose farm location">
      <form className="location-search-form" onSubmit={searchPlaces}>
        <label htmlFor="location-search">Search village, town, district, or address</label>
        <div className="location-search-controls">
          <input
            id="location-search"
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            minLength={3}
            maxLength={120}
            placeholder="Type a place and press Search"
          />
          <button type="submit" className="secondary-button" disabled={searching}>
            {searching ? "Searching…" : "Search"}
          </button>
        </div>
        <p className="location-picker-note">Search runs only when you press the button; no autocomplete requests are sent.</p>
      </form>

      {searchResults.length > 0 && (
        <ul className="location-search-results" aria-label="Search results">
          {searchResults.map((place) => (
            <li key={`${place.latitude},${place.longitude},${place.location_name}`}>
              <button type="button" onClick={() => selectSearchResult(place)}>
                <strong>{place.location_name}</strong>
                <span>{Number(place.latitude).toFixed(5)}, {Number(place.longitude).toFixed(5)}</span>
              </button>
            </li>
          ))}
        </ul>
      )}

      {error && <p className="form-error" role="alert">{error}</p>}
      {status && <p className="location-picker-note" role="status">{status}</p>}

      <MapContainer
        className="farm-location-map"
        center={selected ? [selected.latitude, selected.longitude] : [20, 0]}
        zoom={selected ? 12 : 2}
        scrollWheelZoom={false}
        aria-label="Map for selecting farm location"
        whenReady={() => setMapReady(true)}
      >
        <TileLayer
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">OpenStreetMap contributors</a>'
        />
        <MapInteractions selected={selected} onSelect={setSelected} />
      </MapContainer>
      {!mapReady && <p className="location-picker-note" role="status">Loading map…</p>}
      <p className="location-picker-note">Tap or click the map to place or move the marker.</p>

      <LocationConsent onDetected={(location) => {
        const selection = locationFromGps(location);
        if (!isValidCoordinatePair(selection.latitude, selection.longitude)) {
          setError("Your device returned invalid coordinates. Select a valid point on the map.");
          return;
        }
        setSelected(selection);
        setError(null);
        setStatus("Current location selected. Confirm it only if this is your farm.");
      }} />

      {selected && (
        <div className="location-confirmation">
          <strong>{selected.location_name ?? "Selected coordinates"}</strong>
          <p>Latitude: {selected.latitude.toFixed(6)}</p>
          <p>Longitude: {selected.longitude.toFixed(6)}</p>
          {!selected.location_name && (
            <button
              type="button"
              className="secondary-button"
              onClick={resolveSelectedPlace}
              disabled={resolving}
            >
              {resolving ? "Finding nearby place…" : "Find nearby place"}
            </button>
          )}
          <div className="location-actions">
            <button
              type="button"
              className="primary-button"
              onClick={() => void onConfirm(selected)}
              disabled={saving}
            >
              {saving ? "Saving location…" : confirmLabel}
            </button>
            <button type="button" className="secondary-button" onClick={onCancel} disabled={saving}>
              Cancel
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
