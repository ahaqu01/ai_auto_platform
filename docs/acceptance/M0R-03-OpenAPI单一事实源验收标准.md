# M0R-03 OpenAPI 单一事实源验收标准

> Status: READY
> Work package: M0R-03
> Baseline: `2121145`
> Scope: runtime schema export, controlled snapshot and drift detection

## 1. Objective

FastAPI runtime OpenAPI is the only source of truth. The repository stores a deterministic JSON snapshot generated from the runtime application. CI and local tests must fail whenever runtime API changes without regenerating and reviewing the snapshot.

## 2. Acceptance criteria

| ID | Criterion | Evidence |
|---|---|---|
| OAS-01 | `packages/contracts/openapi.json` is generated from `platform_api.main:create_app` | exporter test |
| OAS-02 | Re-running export without code changes produces byte-identical output | deterministic export test |
| OAS-03 | Runtime schema and controlled snapshot are deeply equal | contract drift test |
| OAS-04 | Snapshot includes live health, organizations and organization-project paths | path assertions |
| OAS-05 | Protected operations declare HTTP Bearer security | security assertions |
| OAS-06 | No protected operation exposes `user_id` as caller identity | parameter assertions |
| OAS-07 | Every operation has a unique, non-empty operationId | contract test |
| OAS-08 | Legacy incomplete hand-maintained YAML is removed to prevent two truths | repository check |
| OAS-09 | Export command is documented and executable from repository root | README/script verification |
| OAS-10 | Full API/Web/Agent regression remains green | full verification |

## 3. Change control

Any API change must include:

1. Runtime route/schema changes.
2. Tests written before implementation where behavior changes.
3. Regenerated `openapi.json`.
4. Reviewed snapshot diff with compatibility classification.
5. Updated acceptance/API documentation when semantics change.

Direct manual edits to `openapi.json` are prohibited.

## 4. Test-first requirement

Before the exporter and snapshot are implemented, the new contract test must be executed and fail because `packages/contracts/openapi.json` does not exist or differs from runtime. A failure caused by import/environment damage is not acceptable evidence.

## 5. Completion definition

This work package can reach `IMPLEMENTED_LOCAL` only after OAS-01 through OAS-10 pass. It cannot reach `REVIEWED` or `ACCEPTED` without independent review and CI/Staging evidence.
