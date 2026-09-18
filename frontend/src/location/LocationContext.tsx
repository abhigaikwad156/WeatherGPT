import { createContext, type PropsWithChildren, useCallback, useContext, useEffect, useState } from "react";

import { ApiError } from "../api/client";
import type { CurrentLocation } from "../api/types";
import { weatherGptApi } from "../api/weatherGpt";

export type LocationErrorKind = "permission-denied" | "unavailable" | "timeout" | "unsupported" | "backend-error";

type LocationContextValue = {
  currentLocation: CurrentLocation | null;
  loadingSavedLocation: boolean;
  locationLoading: boolean;
  errorKind: LocationErrorKind | null;
  refreshCurrentLocation: () => Promise<void>;
  detectAndSaveCurrentLocation: () => Promise<CurrentLocation | null>;
  clearLocationError: () => void;
};

const LocationContext = createContext<LocationContextValue | null>(null);

function readBrowserLocation(): Promise<GeolocationPosition> {
  return new Promise((resolve, reject) => {
    navigator.geolocation.getCurrentPosition(resolve, reject, {
      enableHighAccuracy: true,
      timeout: 10_000,
      maximumAge: 0
    });
  });
}

function toLocationErrorKind(error: unknown): LocationErrorKind {
  if (error instanceof ApiError) return "backend-error";
  if (typeof error === "object" && error !== null && "code" in error) {
    switch ((error as GeolocationPositionError).code) {
      case 1:
        return "permission-denied";
      case 3:
        return "timeout";
      default:
        return "unavailable";
    }
  }
  return "unavailable";
}

export function LocationProvider({ children }: PropsWithChildren) {
  const [currentLocation, setCurrentLocation] = useState<CurrentLocation | null>(null);
  const [loadingSavedLocation, setLoadingSavedLocation] = useState(true);
  const [locationLoading, setLocationLoading] = useState(false);
  const [errorKind, setErrorKind] = useState<LocationErrorKind | null>(null);

  const refreshCurrentLocation = useCallback(async () => {
    setLoadingSavedLocation(true);
    try {
      setCurrentLocation(await weatherGptApi.getCurrentLocation());
    } catch (error) {
      if (!(error instanceof ApiError && error.status === 404)) setErrorKind("backend-error");
      setCurrentLocation(null);
    } finally {
      setLoadingSavedLocation(false);
    }
  }, []);

  useEffect(() => {
    void refreshCurrentLocation();
  }, [refreshCurrentLocation]);

  const detectAndSaveCurrentLocation = useCallback(async () => {
    if (!("geolocation" in navigator)) {
      setErrorKind("unsupported");
      return null;
    }
    setLocationLoading(true);
    setErrorKind(null);
    try {
      const position = await readBrowserLocation();
      const location = await weatherGptApi.saveCurrentLocation({
        latitude: position.coords.latitude,
        longitude: position.coords.longitude,
        accuracy_meters: position.coords.accuracy
      });
      setCurrentLocation(location);
      return location;
    } catch (error) {
      setErrorKind(toLocationErrorKind(error));
      return null;
    } finally {
      setLocationLoading(false);
    }
  }, []);

  const value = {
    currentLocation,
    loadingSavedLocation,
    locationLoading,
    errorKind,
    refreshCurrentLocation,
    detectAndSaveCurrentLocation,
    clearLocationError: () => setErrorKind(null)
  };

  return <LocationContext.Provider value={value}>{children}</LocationContext.Provider>;
}

export function useCurrentLocation() {
  const context = useContext(LocationContext);
  if (!context) throw new Error("useCurrentLocation must be used within LocationProvider");
  return context;
}
