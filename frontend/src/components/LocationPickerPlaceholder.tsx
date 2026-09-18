import { useState } from "react";

/** Integration point for a future map or search provider; it does not collect coordinates itself. */
export function LocationPickerPlaceholder() {
  const [message, setMessage] = useState<string | null>(null);

  return <div className="location-picker-options"><div className="location-actions"><button type="button" className="secondary-button" onClick={() => setMessage("Map selection will be available here soon.")}>Pick location on map</button><button type="button" className="secondary-button" onClick={() => setMessage("Location search will be available here soon.")}>Search for a location</button></div>{message && <p className="location-picker-note" role="status">{message}</p>}</div>;
}
