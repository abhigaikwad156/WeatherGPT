import { type FormEvent, useEffect, useState } from "react";

import {
  CROP_HEALTH_SYMPTOMS,
  type Crop,
  type CropHealthSymptom
} from "../api/types";
import { weatherGptApi } from "../api/weatherGpt";
import { Card, EmptyState, ErrorState, LoadingState } from "../components/ui";
import { useResource } from "../hooks/useResource";

const symptomLabels: Record<CropHealthSymptom, string> = {
  leaf_spots: "Leaf spots",
  yellowing: "Yellowing",
  wilting: "Wilting",
  white_powder: "White powder",
  leaf_curling: "Leaf curling",
  leaf_holes: "Leaf holes",
  stem_damage: "Stem damage",
  fruit_damage: "Fruit damage",
  root_rot: "Root rot",
  stunted_growth: "Stunted growth",
  other: "Other"
};

const durationOptions = [1, 2, 3, 7, 14, 30, 60, 90, 180, 365];

export function CropHealthPage() {
  const farms = useResource(weatherGptApi.getFarms);
  const reports = useResource(weatherGptApi.getCropHealthReports);
  const [farmId, setFarmId] = useState("");
  const [cropId, setCropId] = useState("");
  const [crops, setCrops] = useState<Crop[]>([]);
  const [loadingCrops, setLoadingCrops] = useState(false);
  const [cropRetry, setCropRetry] = useState(0);
  const [cropError, setCropError] = useState<string | null>(null);
  const [symptoms, setSymptoms] = useState<CropHealthSymptom[]>([]);
  const [durationDays, setDurationDays] = useState(1);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const selectedFarm = farms.data?.find((farm) => farm.id === farmId);
  const selectedCrop = crops.find((crop) => crop.id === cropId);

  useEffect(() => {
    if (!farmId && farms.data?.length) setFarmId(farms.data[0].id);
  }, [farmId, farms.data]);

  useEffect(() => {
    let active = true;
    setCropId("");
    setCrops([]);
    setCropError(null);
    if (!farmId) return () => { active = false; };
    setLoadingCrops(true);
    void weatherGptApi.getFarmCrops(farmId)
      .then((result) => {
        if (active) setCrops(result);
      })
      .catch((error: unknown) => {
        if (active) setCropError(error instanceof Error ? error.message : "Unable to load crops.");
      })
      .finally(() => {
        if (active) setLoadingCrops(false);
      });
    return () => { active = false; };
  }, [cropRetry, farmId]);

  const toggleSymptom = (symptom: CropHealthSymptom) => {
    setSymptoms((current) =>
      current.includes(symptom) ? current.filter((item) => item !== symptom) : [...current, symptom]
    );
  };

  const submitReport = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const formElement = event.currentTarget;
    if (!farmId || !cropId || symptoms.length === 0) {
      setFormError("Choose a farm, crop, and at least one symptom.");
      return;
    }
    const form = new FormData(formElement);
    setSaving(true);
    setFormError(null);
    setSuccessMessage(null);
    try {
      await weatherGptApi.createCropHealthReport({
        farm_id: farmId,
        crop_id: cropId,
        symptoms,
        duration_days: durationDays,
        notes: String(form.get("notes") ?? "").trim() || undefined
      });
      setSymptoms([]);
      setDurationDays(1);
      formElement.reset();
      setSuccessMessage("Your crop health report was saved.");
      await reports.refresh();
    } catch (error) {
      setFormError(error instanceof Error ? error.message : "Unable to save this report.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <p className="eyebrow">WeatherGPT</p>
          <h1>Crop health</h1>
          <p>Record crop symptoms to keep a history for your farms.</p>
        </div>
      </header>

      {farms.loading ? <LoadingState label="Loading your farms…" /> : farms.error ? (
        <ErrorState message={farms.error} retry={farms.refresh} />
      ) : !farms.data?.length ? (
        <Card><EmptyState title="No farm available" description="Add a farm before recording crop health." /></Card>
      ) : (
        <Card>
          <div className="card-heading">
            <div><p className="eyebrow">New report</p><h2>What are you observing?</h2></div>
          </div>
          <form className="farm-form crop-health-form" onSubmit={submitReport}>
            <div className="form-row">
              <label htmlFor="health-farm">Farm
                <select id="health-farm" value={farmId} required onChange={(event) => setFarmId(event.target.value)}>
                  <option value="">Select a farm</option>
                  {farms.data.map((farm) => <option key={farm.id} value={farm.id}>{farm.name}</option>)}
                </select>
              </label>
              <label htmlFor="health-crop">Crop
                <select id="health-crop" value={cropId} required disabled={!farmId || loadingCrops || !!cropError}
                  onChange={(event) => setCropId(event.target.value)}>
                  <option value="">{loadingCrops ? "Loading crops…" : "Select a crop"}</option>
                  {crops.map((crop) => <option key={crop.id} value={crop.id}>{crop.name}</option>)}
                </select>
              </label>
            </div>
            {cropError && <div className="crop-health-crop-error" role="alert">
              <p className="form-error">{cropError}</p>
              <button className="secondary-button" type="button" onClick={() => setCropRetry((value) => value + 1)}>
                Retry loading crops
              </button>
            </div>}
            {!loadingCrops && farmId && !cropError && crops.length === 0 && (
              <p className="crop-health-hint">Add a crop to this farm before submitting a report.</p>
            )}
            <fieldset className="symptom-fieldset">
              <legend>Symptoms <span>(select all that apply)</span></legend>
              <div className="symptom-grid">
                {CROP_HEALTH_SYMPTOMS.map((symptom) => (
                  <label className={`symptom-option ${symptoms.includes(symptom) ? "selected" : ""}`} key={symptom}>
                    <input type="checkbox" checked={symptoms.includes(symptom)}
                      onChange={() => toggleSymptom(symptom)} />
                    <span>{symptomLabels[symptom]}</span>
                  </label>
                ))}
              </div>
            </fieldset>
            <label htmlFor="symptom-duration">How long have you noticed this?
              <select id="symptom-duration" value={durationDays}
                onChange={(event) => setDurationDays(Number(event.target.value))}>
                {durationOptions.map((days) => <option key={days} value={days}>{days} {days === 1 ? "day" : "days"}</option>)}
              </select>
            </label>
            <label htmlFor="health-notes">Notes <span className="optional-label">(optional)</span>
              <textarea id="health-notes" name="notes" rows={4} maxLength={2000}
                placeholder="Add any details that may help you remember what you observed." />
            </label>
            {formError && <p className="form-error" role="alert">{formError}</p>}
            {successMessage && <p className="form-success" role="status">{successMessage}</p>}
            <button className="primary-button" type="submit"
              disabled={saving || !selectedFarm || !selectedCrop || loadingCrops || !!cropError}>
              {saving ? "Saving report…" : "Save crop health report"}
            </button>
          </form>
        </Card>
      )}

      <Card className="crop-health-history">
        <div className="card-heading">
          <div><p className="eyebrow">Your records</p><h2>Report history</h2></div>
          <button className="secondary-button" type="button" onClick={() => void reports.refresh()}
            disabled={reports.loading}>Refresh</button>
        </div>
        {reports.loading ? <LoadingState label="Loading report history…" /> : reports.error ? (
          <ErrorState message={reports.error} retry={() => void reports.refresh()} />
        ) : reports.data?.length ? (
          <div className="stack">
            {reports.data.map((report) => (
              <article className="crop-health-report" key={report.id}>
                <div className="crop-health-report-heading">
                  <div><h3>{report.crop_name}</h3><p>{report.farm_name}</p></div>
                  <time dateTime={report.created_at}>{new Date(report.created_at).toLocaleString()}</time>
                </div>
                <div className="symptom-tags" aria-label="Reported symptoms">
                  {report.symptoms.map((symptom) => <span key={symptom}>{symptomLabels[symptom]}</span>)}
                </div>
                <p className="crop-health-duration">Observed for {report.duration_days} {report.duration_days === 1 ? "day" : "days"}</p>
                {report.notes && <p className="crop-health-notes">{report.notes}</p>}
              </article>
            ))}
          </div>
        ) : <EmptyState title="No reports yet" description="Your crop health reports will appear here after you save one." />}
      </Card>
    </div>
  );
}
