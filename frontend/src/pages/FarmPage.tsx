import { type FormEvent, useCallback, useRef, useState } from "react";

import type { Crop, Farm, FarmLocation } from "../api/types";
import { weatherGptApi } from "../api/weatherGpt";
import { LocationMapPicker, type FarmLocationSelection } from "../components/LocationMapPicker";
import { Card, EmptyState, ErrorState, LoadingState } from "../components/ui";
import { useResource } from "../hooks/useResource";
import { locationDisplayName } from "../location/locationDisplay";

function FarmCard({ farm }: { farm: Farm }) {
  const [editingLocation, setEditingLocation] = useState(false);
  const [savingLocation, setSavingLocation] = useState(false);
  const [locationError, setLocationError] = useState<string | null>(null);
  const loadFarmDetails = useCallback(
    async () => Promise.all([weatherGptApi.getFarmLocation(farm.id), weatherGptApi.getFarmCrops(farm.id)]),
    [farm.id]
  );
  const details = useResource(loadFarmDetails);
  const farmLocation = details.data?.[0] ?? null;
  const crops = details.data?.[1] ?? [];

  async function confirmFarmLocation(selection: FarmLocationSelection) {
    setSavingLocation(true);
    setLocationError(null);
    try {
      await weatherGptApi.updateFarmLocation(farm.id, {
        ...selection,
        location_name: selection.location_name ?? undefined
      });
      await details.refresh();
      setEditingLocation(false);
    } catch {
      setLocationError("We couldn't save this as your farm location. Please try again.");
    } finally {
      setSavingLocation(false);
    }
  }

  return <Card className="farm-summary-card">
    <div className="card-heading"><div><p className="eyebrow">My farm</p><h2>{farm.name}</h2></div><button type="button" className="secondary-button" onClick={() => { setLocationError(null); setEditingLocation((open) => !open); }} disabled={details.loading}>Edit farm location</button></div>
    {details.loading ? <LoadingState label="Loading farm location…" /> : details.error ? <ErrorState message={details.error} retry={details.refresh} /> : <div className="farm-summary-details"><p className="farm-location-label">📍 {locationDisplayName(farmLocation)}</p><dl><div><dt>Latitude</dt><dd>{Number(farmLocation?.latitude).toFixed(5)}</dd></div><div><dt>Longitude</dt><dd>{Number(farmLocation?.longitude).toFixed(5)}</dd></div><div><dt>Crop</dt><dd>{crops[0]?.name ?? "No crop added"}</dd></div><div><dt>Soil</dt><dd>{farm.soil_type || "Not set"}</dd></div></dl></div>}
    {editingLocation && <div className="farm-location-editor"><h3>Update farm location</h3><LocationMapPicker initialLocation={farmLocation} onConfirm={confirmFarmLocation} onCancel={() => setEditingLocation(false)} saving={savingLocation} confirmLabel="Confirm farm location" />{locationError && <p className="form-error" role="alert">{locationError}</p>}</div>}
  </Card>;
}

export function FarmPage() {
  const state = useResource(weatherGptApi.getFarms);
  const [locationSelection, setLocationSelection] = useState<FarmLocationSelection | null>(null);
  const [selectingLocation, setSelectingLocation] = useState(true);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const formRef = useRef<HTMLFormElement>(null);

  async function createFarm(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!locationSelection) {
      setFormError("Choose and confirm your farm location before saving your farm.");
      return;
    }
    const formElement = event.currentTarget;
    setSaving(true);
    setFormError(null);
    const form = new FormData(formElement);
    try {
      await weatherGptApi.createFarm({
        name: String(form.get("name")).trim(),
        latitude: locationSelection.latitude,
        longitude: locationSelection.longitude,
        location_name: locationSelection.location_name ?? undefined,
        area_hectares: Number(form.get("area")),
        soil_type: String(form.get("soilType")).trim() || undefined,
        irrigation_type: String(form.get("irrigationType")).trim() || undefined,
        soil_moisture_percent: form.get("soilMoisture") ? Number(form.get("soilMoisture")) : undefined
      });
      formRef.current?.reset();
      setLocationSelection(null);
      setSelectingLocation(true);
      await state.refresh();
    } catch {
      setFormError("We couldn't save your farm. Please try again.");
    } finally {
      setSaving(false);
    }
  }

  function confirmNewFarmLocation(selection: FarmLocationSelection) {
    setLocationSelection(selection);
    setSelectingLocation(false);
    setFormError(null);
  }

  return <div className="page">
    <header className="page-header"><div><p className="eyebrow">WeatherGPT</p><h1>My farm</h1><p>Set your farm location once to unlock local weather and crop advice.</p></div></header>
    {state.loading ? <LoadingState /> : state.error ? <ErrorState message={state.error} retry={state.refresh} /> : <>
      {state.data?.length ? <div className="stack">{state.data.map((farm) => <FarmCard key={farm.id} farm={farm} />)}</div> : <Card><EmptyState title="No farm added yet" description="Choose your farm location and enter the details below." /></Card>}
      <Card className="farm-form-card">
        <div className="card-heading"><div><p className="eyebrow">Farm details</p><h2>Add a farm</h2></div></div>
        <form ref={formRef} className="farm-form" onSubmit={createFarm}>
          <label>Farm name<input name="name" required minLength={2} placeholder="My farm" /></label>
          <div className="farm-location-setup">
            <h3>Farm location</h3>
            {locationSelection ? (
              <div className="location-confirmation">
                <strong>{locationSelection.location_name ?? "Selected farm coordinates"}</strong>
                <p>Latitude: {locationSelection.latitude.toFixed(6)}</p>
                <p>Longitude: {locationSelection.longitude.toFixed(6)}</p>
                <button type="button" className="secondary-button" onClick={() => { setLocationSelection(null); setSelectingLocation(true); }}>Change location</button>
              </div>
            ) : selectingLocation ? (
              <LocationMapPicker
                onConfirm={confirmNewFarmLocation}
                onCancel={() => setSelectingLocation(false)}
              />
            ) : (
              <button type="button" className="secondary-button" onClick={() => setSelectingLocation(true)}>Choose farm location</button>
            )}
          </div>
          <div className="form-row"><label>Area (hectares)<input name="area" required type="number" step="0.01" min="0.01" placeholder="2" /></label><label>Soil type<input name="soilType" placeholder="Black soil" /></label></div>
          <div className="form-row"><label>Irrigation type<input name="irrigationType" placeholder="Drip / rain-fed" /></label><label>Soil moisture %<input name="soilMoisture" type="number" min="0" max="100" step="0.1" placeholder="Optional" /></label></div>
          {formError && <p className="form-error" role="alert">{formError}</p>}
          <button className="primary-button" disabled={saving || !locationSelection}>{saving ? "Saving farm…" : "Save farm"}</button>
        </form>
      </Card>
    </>}
  </div>;
}
