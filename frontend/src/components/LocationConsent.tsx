import { useState } from "react";

import { useCurrentLocation, type LocationErrorKind } from "../location/LocationContext";
import { locationDisplayName } from "../location/locationDisplay";

const errorMessages: Record<LocationErrorKind, string> = {
  "permission-denied": "Location permission was denied.",
  unavailable: "Unable to determine your location.",
  timeout: "Location detection timed out.",
  unsupported: "Location services are not supported by this browser.",
  "backend-error": "Location was detected, but we couldn't save it."
};

export function LocationConsent({ onDetected }: { onDetected?: () => void }) {
  const [explaining, setExplaining] = useState(false);
  const { clearLocationError, currentLocation, detectAndSaveCurrentLocation, errorKind, locationLoading } =
    useCurrentLocation();

  async function allowLocation() {
    const location = await detectAndSaveCurrentLocation();
    if (location) onDetected?.();
  }

  if (!explaining) {
    return <button type="button" className="primary-button" onClick={() => setExplaining(true)}>⌖ Use my current location</button>;
  }

  return <div className="location-consent" aria-live="polite">
    <p>WeatherGPT uses your location to provide local weather and agricultural advisories.</p>
    {errorKind ? <><p className="form-error" role="alert">{errorMessages[errorKind]}</p><div className="location-actions"><button type="button" className="primary-button" onClick={allowLocation} disabled={locationLoading}>{locationLoading ? "Detecting your location…" : "Try again"}</button><button type="button" className="secondary-button" onClick={() => { clearLocationError(); setExplaining(false); }}>Choose location manually</button></div></> : <div className="location-actions"><button type="button" className="primary-button" onClick={allowLocation} disabled={locationLoading}>{locationLoading ? "Detecting your location…" : "Allow location"}</button><button type="button" className="secondary-button" onClick={() => setExplaining(false)} disabled={locationLoading}>Not now</button></div>}
    {currentLocation && !locationLoading && !errorKind && <p className="location-success">Location detected · 📍 {locationDisplayName(currentLocation)}</p>}
  </div>;
}
