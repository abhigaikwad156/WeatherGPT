import { createContext, type PropsWithChildren, useCallback, useContext, useEffect, useState } from "react";

import { ApiError } from "../api/client";
import type { CurrentLocation } from "../api/types";
import { weatherGptApi } from "../api/weatherGpt";

export type LocationErrorKind = "permission-denied" | "unavailable" | "timeout" | "unsupported" | "backend-error";
export type LocationLoadingPhase = "getting" | "saving" | null;

type LocationContextValue = {
  currentLocation: CurrentLocation | null;
  loadingSavedLocation: boolean;
  locationLoading: boolean;
  locationPhase: LocationLoadingPhase;
  errorKind: LocationErrorKind | null;
  refreshCurrentLocation: () => Promise<void>;
  detectAndSaveCurrentLocation: () => Promise<CurrentLocation | null>;
  clearLocationError: () => void;
};

const LocationContext = createContext<LocationContextValue | null>(null);

function createLocationDebugId(): string | undefined {
  if (!import.meta.env.DEV) return undefined;
  return `location-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

function logLocationDebug(source: string, values: Record<string, number | string | null | undefined>) {
  if (import.meta.env.DEV) console.debug("[LOCATION_DEBUG]", { source, ...values });
}

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
  const [locationPhase, setLocationPhase] = useState<LocationLoadingPhase>(null);
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
    if (!navigator.geolocation) {
      setErrorKind("unsupported");
      return null;
    }
    setLocationLoading(true);
    setLocationPhase("getting");
    setErrorKind(null);
    try {
      const position = await readBrowserLocation();
      const requestId = createLocationDebugId();
      const payload = {
        latitude: position.coords.latitude,
        longitude: position.coords.longitude,
        accuracy_meters: position.coords.accuracy
      };
      logLocationDebug("browser", { request_id: requestId, ...payload });
      setLocationPhase("saving");
      logLocationDebug("frontend_request", { request_id: requestId, ...payload });
      const location = await weatherGptApi.saveCurrentLocation(payload, requestId);
      logLocationDebug("frontend_response_state", {
        request_id: requestId,
        latitude: location.latitude,
        longitude: location.longitude,
        location_name: location.location_name
      });
      setCurrentLocation(location);
      return location;
    } catch (error) {
      setErrorKind(toLocationErrorKind(error));
      return null;
    } finally {
      setLocationLoading(false);
      setLocationPhase(null);
    }
  }, []);

  const value = {
    currentLocation,
    loadingSavedLocation,
    locationLoading,
    locationPhase,
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
