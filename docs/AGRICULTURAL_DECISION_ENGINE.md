# Agricultural Decision Engine

## Purpose and boundaries

The decision engine is a deterministic rules layer. It does not ask an LLM to decide
whether to irrigate, spray, sow, or respond to weather risk. It accepts normalized
weather data and farm/crop context and returns structured `Decision` objects.

Each result includes:

- `decision`: the operational outcome (`APPLY`, `WAIT`, `SUITABLE`, `NOT_SUITABLE`,
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

Rules other than irrigation are configured in
[`agricultural_thresholds.json`](../backend/app/agriculture/data/agricultural_thresholds.json).
The shipped file intentionally contains `null` values and no irrigation profiles. This avoids
presenting universal agronomic thresholds as scientific facts. A deployment must populate
profiles only with values reviewed for their crop, growth stage, soil type, region,
irrigation practice, and sensor contract.

An unset value disables that rule. The engine returns `NEEDS_INPUT` rather than silently
falling back to a guessed threshold. Tests inject explicit fixture-only
`AgriculturalThresholds` objects so rule behavior is reproducible and reviewable.

## Rules

### Irrigation

The engine first selects one unambiguous, crop-specific irrigation profile. Profiles can be
scoped by growth stage, soil type, irrigation type, and region; there is no global irrigation
fallback. A profile also records its soil-moisture measurement basis and sensor depth, its
forecast horizon, and reviewable source metadata. A profile must identify a reviewer and cannot
be effective in the future before it is eligible for a decision.

The engine returns `NEEDS_INPUT` when no profile matches, either numerical threshold remains
null, or soil-moisture or forecast-rainfall evidence is missing. It waits when soil moisture
is at or above the profile sufficiency threshold, or forecast rainfall meets the profile
lookahead threshold; only then can it recommend applying irrigation.

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
