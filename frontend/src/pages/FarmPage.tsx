import { type FormEvent, useState } from "react";

import type { Farm } from "../api/types";
import { weatherGptApi } from "../api/weatherGpt";
import { Card, EmptyState, ErrorState, LoadingState } from "../components/ui";
import { useResource } from "../hooks/useResource";

export function FarmPage() {
  const state = useResource(weatherGptApi.getFarms);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  async function createFarm(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setFormError(null);
    const form = new FormData(event.currentTarget);
    try {
      await weatherGptApi.createFarm({
        name: String(form.get("name")).trim(),
        latitude: Number(form.get("latitude")),
        longitude: Number(form.get("longitude")),
        area_hectares: Number(form.get("area")),
        soil_type: String(form.get("soilType")).trim() || undefined,
        irrigation_type: String(form.get("irrigationType")).trim() || undefined,
        soil_moisture_percent: form.get("soilMoisture")
          ? Number(form.get("soilMoisture"))
          : undefined
      });
      event.currentTarget.reset();
      await state.refresh();
    } catch (caught) {
      setFormError(caught instanceof Error ? caught.message : "Unable to save your farm.");
    } finally {
      setSaving(false);
    }
  }

  return <div className="page">
    <header className="page-header">
      <div><p className="eyebrow">WeatherGPT</p><h1>My farm</h1><p>Add your farm once to unlock weather and crop advice.</p></div>
    </header>
    {state.loading ? <LoadingState /> : state.error ? <ErrorState message={state.error} retry={state.refresh} /> : <>
      {state.data?.length ? <div className="stack">{state.data.map((farm: Farm) => <Card key={farm.id}><p className="eyebrow">Farm location</p><h2>{farm.name}</h2><p>{farm.latitude}, {farm.longitude}</p><p>{farm.area_hectares ?? "—"} hectares · {farm.soil_type || "Soil not set"} · {farm.irrigation_type || "Irrigation not set"}</p></Card>)}</div> : <Card><EmptyState title="No farm added yet" description="Enter your farm details below so WeatherGPT can use your location." /></Card>}
      <Card className="farm-form-card">
        <div className="card-heading"><div><p className="eyebrow">Farm details</p><h2>Add a farm</h2></div></div>
        <form className="farm-form" onSubmit={createFarm}>
          <label>Farm name<input name="name" required minLength={2} placeholder="My farm" /></label>
          <div className="form-row"><label>Latitude<input name="latitude" required type="number" step="any" min="-90" max="90" placeholder="18.52" /></label><label>Longitude<input name="longitude" required type="number" step="any" min="-180" max="180" placeholder="73.85" /></label></div>
          <div className="form-row"><label>Area (hectares)<input name="area" required type="number" step="0.01" min="0.01" placeholder="2" /></label><label>Soil type<input name="soilType" placeholder="Black soil" /></label></div>
          <div className="form-row"><label>Irrigation type<input name="irrigationType" placeholder="Drip / rain-fed" /></label><label>Soil moisture %<input name="soilMoisture" type="number" min="0" max="100" step="0.1" placeholder="Optional" /></label></div>
          {formError && <p className="form-error" role="alert">{formError}</p>}
          <button className="primary-button" disabled={saving}>{saving ? "Saving farm…" : "Save my farm"}</button>
        </form>
      </Card>
    </>}
  </div>;
}
