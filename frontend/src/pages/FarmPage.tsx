import { type FormEvent, useCallback, useRef, useState } from "react";

import type { Crop, Farm } from "../api/types";
import { weatherGptApi } from "../api/weatherGpt";
import { LocationConsent } from "../components/LocationConsent";
import { LocationPickerPlaceholder } from "../components/LocationPickerPlaceholder";
import { Card, EmptyState, ErrorState, LoadingState } from "../components/ui";
import { useResource } from "../hooks/useResource";
import { useCurrentLocation } from "../location/LocationContext";
import { locationDisplayName } from "../location/locationDisplay";

function FarmCard({ farm }: { farm: Farm }) {
  const [editingLocation, setEditingLocation] = useState(false);
  const [locationDetected, setLocationDetected] = useState(false);
  const [savingLocation, setSavingLocation] = useState(false);
  const [locationError, setLocationError] = useState<string | null>(null);
  const { currentLocation } = useCurrentLocation();
  const loadFarmDetails = useCallback(
    async () => Promise.all([weatherGptApi.getFarmLocation(farm.id), weatherGptApi.getFarmCrops(farm.id)]),
    [farm.id]
  );
  const details = useResource(loadFarmDetails);
  const [farmLocation, crops] = details.data ?? [null, [] as Crop[]];

  async function confirmFarmLocation() {
    if (!locationDetected || !currentLocation) return;
    setSavingLocation(true);
    setLocationError(null);
    try {
      await weatherGptApi.useCurrentLocationForFarm(farm.id);
      await details.refresh();
      setEditingLocation(false);
      setLocationDetected(false);
    } catch {
      setLocationError("We couldn't save this as your farm location. Please try again.");
    } finally {
      setSavingLocation(false);
    }
  }

  return <Card className="farm-summary-card">
    <div className="card-heading"><div><p className="eyebrow">My farm</p><h2>{farm.name}</h2></div><button type="button" className="secondary-button" onClick={() => setEditingLocation((open) => !open)}>Edit farm location</button></div>
    {details.loading ? <LoadingState label="Loading farm location…" /> : details.error ? <ErrorState message={details.error} retry={details.refresh} /> : <div className="farm-summary-details"><p className="farm-location-label">📍 {locationDisplayName(farmLocation)}</p><dl><div><dt>Crop</dt><dd>{crops[0]?.name ?? "No crop added"}</dd></div><div><dt>Growth stage</dt><dd>{crops[0]?.growth_stage ?? "Not set"}</dd></div><div><dt>Soil</dt><dd>{farm.soil_type || "Not set"}</dd></div><div><dt>Irrigation</dt><dd>{farm.irrigation_type || "Not set"}</dd></div></dl></div>}
    {editingLocation && <div className="farm-location-editor"><h3>Update farm location</h3>{locationDetected && currentLocation ? <div className="location-confirmation"><strong>Location detected</strong><p>📍 {locationDisplayName(currentLocation)}</p><p>Is this your farm location?</p><div className="location-actions"><button type="button" className="primary-button" onClick={confirmFarmLocation} disabled={savingLocation}>{savingLocation ? "Saving farm location…" : "Confirm farm"}</button><button type="button" className="secondary-button" onClick={() => setLocationDetected(false)} disabled={savingLocation}>Choose another location</button></div></div> : <><LocationConsent onDetected={() => setLocationDetected(true)} /><LocationPickerPlaceholder /></>}{locationError && <p className="form-error" role="alert">{locationError}</p>}</div>}
  </Card>;
}

export function FarmPage() {
  const state = useResource(weatherGptApi.getFarms);
  const { currentLocation } = useCurrentLocation();
  const [locationDetected, setLocationDetected] = useState(false);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const formRef = useRef<HTMLFormElement>(null);

  async function createFarm(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!locationDetected || !currentLocation) {
      setFormError("Choose your farm location before saving your farm.");
      return;
    }
    const formElement = event.currentTarget;
    setSaving(true);
    setFormError(null);
    const form = new FormData(formElement);
    try {
      const farm = await weatherGptApi.createFarm({
        name: String(form.get("name")).trim(),
        latitude: Number(currentLocation.latitude),
        longitude: Number(currentLocation.longitude),
        area_hectares: Number(form.get("area")),
        soil_type: String(form.get("soilType")).trim() || undefined,
        irrigation_type: String(form.get("irrigationType")).trim() || undefined,
        soil_moisture_percent: form.get("soilMoisture") ? Number(form.get("soilMoisture")) : undefined
      });
      await weatherGptApi.useCurrentLocationForFarm(farm.id);
      formRef.current?.reset();
      setLocationDetected(false);
      await state.refresh();
    } catch {
      setFormError("We couldn't save your farm location. Please try again.");
    } finally {
      setSaving(false);
    }
  }

  return <div className="page">
    <header className="page-header"><div><p className="eyebrow">WeatherGPT</p><h1>My farm</h1><p>Set your farm location once to unlock local weather and crop advice.</p></div></header>
    {state.loading ? <LoadingState /> : state.error ? <ErrorState message={state.error} retry={state.refresh} /> : <>
      {state.data?.length ? <div className="stack">{state.data.map((farm) => <FarmCard key={farm.id} farm={farm} />)}</div> : <Card><EmptyState title="No farm added yet" description="Choose your farm location and enter the details below." /></Card>}
      <Card className="farm-form-card">
        <div className="card-heading"><div><p className="eyebrow">Farm details</p><h2>Add a farm</h2></div></div>
        <form ref={formRef} className="farm-form" onSubmit={createFarm}>
          <label>Farm name<input name="name" required minLength={2} placeholder="My farm" /></label>
          <div className="farm-location-setup"><h3>Farm location</h3>{locationDetected && currentLocation ? <div className="location-confirmation"><strong>Location detected</strong><p>📍 {locationDisplayName(currentLocation)}</p><p>Is this your farm location?</p><button type="button" className="secondary-button" onClick={() => setLocationDetected(false)}>Choose another location</button></div> : <><LocationConsent onDetected={() => setLocationDetected(true)} /><LocationPickerPlaceholder /></>}</div>
          <div className="form-row"><label>Area (hectares)<input name="area" required type="number" step="0.01" min="0.01" placeholder="2" /></label><label>Soil type<input name="soilType" placeholder="Black soil" /></label></div>
          <div className="form-row"><label>Irrigation type<input name="irrigationType" placeholder="Drip / rain-fed" /></label><label>Soil moisture %<input name="soilMoisture" type="number" min="0" max="100" step="0.1" placeholder="Optional" /></label></div>
          {formError && <p className="form-error" role="alert">{formError}</p>}
          <button className="primary-button" disabled={saving || !locationDetected}>{saving ? "Saving farm…" : "Confirm farm location and save"}</button>
        </form>
      </Card>
    </>}
  </div>;
}
