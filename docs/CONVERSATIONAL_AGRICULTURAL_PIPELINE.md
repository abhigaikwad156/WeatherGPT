# Conversational Agricultural Pipeline

The chatbot now separates interpretation, trusted data retrieval, deterministic decisions,
knowledge retrieval, and explanation:

`question -> intent/entity extraction -> farmer tools -> weather tools -> decision engine -> RAG -> explanation`

## Interfaces

- `IntentEntityExtractor` identifies location, crop, growth stage, and requested action.
- `FarmerContextTool` resolves only the authenticated user's farm and crop context.
- `WeatherContextTool` supplies persisted weather observations and forecasts.
- `AgriculturalDecisionEngine` produces the authoritative structured decision.
- `RetrievalService` is consulted only when the question requires agricultural knowledge.
- `AgriculturalExplanation` is a presentation boundary. The default explanation reports
  the decision and reasons and cannot modify the decision.

`AgriculturalChatPipeline` accepts these interfaces through dependency injection, making
the flow testable and allowing production adapters to be replaced without changing
business rules.

## Decision authority

The LLM is not used for intent-critical decisions and is not currently required by the
default explanation implementation. If an LLM adapter is added, it must receive the
structured `Decision` and retrieved source-bearing context. It may explain the decision,
but it must not override `decision`, `risk_level`, `confidence`, or `reasons`.

## API response

Agricultural chatbot responses include an `agricultural` metadata object containing:

- decision type and decision
- risk level
- confidence
- reasons
- deterministic flag
- RAG citations when knowledge retrieval was used

Regular weather-only questions continue using the existing weather intent/tool flow.
If farm or crop context is unavailable, the agricultural path does not invent context.
