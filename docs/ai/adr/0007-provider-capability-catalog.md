# ADR-010/011 — Provider capability aliases and reasoning policy

- Status: `ACCEPTED`
- Date: 2026-08-12
- Implemented by: NIF-02
- Database migration: none

## Decision

Business AI code requests a stable internal capability instead of selecting a model name. The accepted aliases are:

```text
FAST_ROUTER
GENERAL_CHAT
DEEP_REASONING
MULTIMODAL_GENERAL
STRUCTURED_EXTRACTION
DOCUMENT_OCR
TRANSLATION
EMBEDDING
RERANK
```

`DOCUMENT_OCR`, `EMBEDDING`, and `RERANK` are vocabulary only. Catalog v1 does not register them as available. In particular, `DOCUMENT_OCR` remains explicitly prohibited through NIF-18 and cannot be reported by the Capability resource.

The accepted internal reasoning policies are `FAST`, `BALANCED`, and `DEEP`. A reviewed Provider profile maps them to API-specific values. For the current Qwen/Fake compatibility profile the mapping is `low`, `medium`, and `high`. Business code does not use Provider-specific reasoning names.

## Catalog and routing contract

- Catalog v1 is loaded from strict `AI_MODEL_CATALOG_JSON`, or from the reviewed single-provider default when blank.
- Every profile has a unique ID, Provider, model, region, capability set, reasoning map, modality set, streaming/custom-tool/structured-output declarations, and version.
- A Provider/region may have only one profile for each capability alias in Catalog v1. Ambiguity fails closed.
- Missing aliases, unknown aliases, prohibited capabilities, incomplete policies, unsupported modalities, and region mismatch fail closed before a Provider call.
- Fallback cannot cross region and cannot silently lower a required capability.
- `AI_PROVIDER_CAPABILITY_ROUTER_ENABLED=false` preserves the exact legacy model, reasoning effort, request limits, JSON/SSE and Drawer behavior.

## Provider request policy

ProviderRequest v2 explicitly carries capability/profile/catalog version, reasoning policy, response format, storage/state/cache policies, Tool choice, built-in/custom Tool posture, parallel Tool posture, modalities, retry/fallback/region policy, and data classification.

The Qwen adapter enforces:

- `store=false`, stateless calls, cache disabled and parallel tools disabled;
- no unregistered built-in Provider tools;
- no cross-region request or fallback;
- no structured output unless the profile supports it, followed by application-side Pydantic validation;
- no Provider reasoning value outside the reviewed profile mapping;
- no retry for authentication, validation/policy errors, requests with Tool definitions or replay, image requests, or after any streamed event;
- at most three attempts with bounded exponential delay for explicitly marked, stateless, text-only, no-tool requests that fail with timeout, 429 or 5xx.

Provider stream v2 expresses text, Tool calls, refusal, incomplete, error, usage and completion. The v1 adapter path preserves its old event sequence while the Router Flag is off.

## Observability and secrets

When v2 is enabled, server logs and additive v2 event fields record Provider name, selected model, capability alias, profile ID, Catalog version and reasoning policy. API Key, Workspace ID, endpoint and Provider error text are never added to response events or Capability output.

## Rollback

Set `AI_PROVIDER_CAPABILITY_ROUTER_ENABLED=false`. The current ProviderRequest v1 path and NIF-01 Golden Contract remain in place; no schema rollback is required.
