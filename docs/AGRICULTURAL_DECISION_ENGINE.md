# Agricultural Decision Engine

## Purpose and boundaries

The decision engine is a deterministic rules layer. It does not ask an LLM to decide
whether to irrigate, spray, sow, or respond to weather risk. It accepts normalized
weather data and farm/crop context and returns structured `Decision` objects.

Each result includes:

- `decision`: the operational outcome (`IRRIGATE`, `DO_NOT_IRRIGATE`, `APPLY`, `WAIT`, `SUITABLE`, `NOT_SUITABLE`,
  `HIGH_RISK`, `LOW_RISK`, or `NEEDS_INPUT`)
- `risk_level`
- `confidence`: confidence in the rule evaluation, not a statistical probability
- `reasons`
- `deterministic: true`
- `ml_prediction`: reserved for a separately validated ML service, currently `null`
- `llm_explanation`: reserved for a presentation-only explanation layer, currently `null`

The LLM may explain a result after the engine runs, but it must not replace the engine
or add weather facts that were not supplied by a trusted weather provider.

## Configuration and scientific safety

Rules and evidence are configured in
[`agricultural_thresholds.json`](../backend/app/agriculture/data/agricultural_thresholds.json).
The shipped file contains no active Maharashtra Sugarcane thresholds. It records the
TNAU drip schedule as Tamil Nadu supporting evidence and as a Maharashtra candidate that
cannot be used until an agronomist approves its local applicability. The retrieved MPKV
bulletin and DARE/ICAR report are recorded as evidence, not decision rules. Historical
numeric records remain inactive because their sources or sensor contracts could not be
verified.

An unset value disables that rule. The engine returns `NEEDS_INPUT` rather than silently
falling back to a guessed threshold. Tests inject explicit fixture-only
`AgriculturalThresholds` objects so rule behavior is reproducible and reviewable.
To deploy reviewed values separately from the packaged defaults, set
`AGRICULTURAL_THRESHOLDS_PATH` to a UTF-8 JSON file. Each enabled top-level threshold must
have a matching `source_notes` entry named after its JSON field; each enabled crop profile
requires `source_notes.crop_profiles.<crop>`. Invalid ranges and untraced values fail at
load time. Irrigation profiles require crop, stage, soil, method, region, source URI,
publisher, source title, source region, and a page or section citation. A profile is actionable
only with `review_status: "approved"`, a named reviewer, and a current effective date.
Soil-moisture rules also require a measurement basis, sensor depth, and a reviewed maximum
measurement age. Schedule rules require source-stated intervals and all source applicability
conditions; they use the crop's recorded last-irrigation date. An unset rule never falls back
to an LLM-generated value.

## Rules

### Irrigation

The engine requires crop, crop age, recorded stage, soil, irrigation method, and region for
Sugarcane. Crop age is calculated from planting date, but a missing or unrecognized growth
stage is requested rather than inferred. Profile matching also checks drip layout and recorded
emitter/lateral specifications when the source requires them.

The operational outcomes are `IRRIGATE`, `DO_NOT_IRRIGATE`, and `NEEDS_INPUT`. A fresh
soil-moisture measurement is considered only when the approved profile states a maximum
measurement age, basis, and sensor depth. Rainfall affects a decision only when a reviewed
rainfall rule exists and complete, fresh rainfall data covers its entire horizon. Otherwise the
response explicitly identifies the weather limitation. If soil moisture is absent or stale, an
approved, fully applicable source schedule can be used; it is labeled `source_schedule` and
requires the last-irrigated date. Sensor-based and schedule-based decisions are distinguished
in the response.

The retrieved TNAU page gives a paired-row drip interval of once every three days based on
evapotranspiration demand and separately describes daily or alternate-day irrigation for a pit
method. These methods are kept separate. The paired-row passage also lists a specific lateral
and emitter configuration. Because this guidance is Tamil Nadu-specific and no reviewed
Maharashtra rule corroborating it was found, it remains `supporting_only`; it cannot produce
an irrigation instruction for a Maharashtra farm. The TNAU stage-wise conventional intervals
and IW/CPE ratios are retained as evidence only and are not transferred to drip or Black Soil.
The separate TNAU Sustainable Sugarcane Initiative passage gives daily or once-in-three-days
drip scheduling based on soil type without mapping soil types to an interval; this remains a
distinct supporting claim. TNAU's FAQ rainfall range is recorded as seasonal context, not as an
irrigation or rainfall-deferral threshold.

The recommendation API and dashboard upsert the latest irrigation decision for each farm
and crop into the existing `recommendations` table. The dashboard renders decisions and
missing inputs, and the crop/farm forms can record growth stage, last irrigation, moisture
measurement time, and drip setup. Irrigation chat uses RAG citations as supporting evidence
but returns the deterministic bilingual explanation directly; Gemini is not allowed to rewrite
or override an irrigation verdict.

### Spraying

The engine waits when wind exceeds the configured maximum, humidity is outside the
configured interval, or forecast rainfall meets the configured wash-off threshold.
It recommends spraying only when the configured weather window is satisfied. Product label
requirements and crop-specific safety intervals remain outside this generic engine.

### Sowing window

The engine marks a window suitable only when temperature and forecast rainfall are both
inside the configured ranges. It does not infer soil workability, seed quality, or local
calendar dates that were not provided.

### Extreme-weather risk

The engine raises high risk when configured temperature, rainfall, or wind limits are
reached, or when the trusted forecast includes a severe-weather signal. Without a configured
rule or trusted severe-weather signal it returns `NEEDS_INPUT`.

### Crop-weather compatibility

The engine compares current temperature with the configured crop profile. It returns
`NOT_SUITABLE` when the value is outside the configured range and `SUITABLE` otherwise.
Humidity and growth-stage compatibility should only be enabled after crop-specific
profiles are added to the configuration.

## Extending the engine

Add a new deterministic module with the same `(AgriculturalInputs, AgriculturalThresholds)
-> Decision` contract, add it to `AgriculturalDecisionEngine.evaluate`, and add focused
tests. Keep provider adapters, ML predictions, and LLM explanations outside the rule
functions.
