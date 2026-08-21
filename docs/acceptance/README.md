# Acceptance Status Index

> Updated: 2026-08-21  
> Authoritative status source: `../CURRENT_STATUS.md`

## Status correction

| Slice | Previous record | Milestone review status | Reason |
|---|---|---|---|
| P0-Auth-01 OIDC JWT and tenant identity | Recorded as passed | `IMPLEMENTED_LOCAL / REOPENED` | No real Keycloak E2E or BFF; strict DTO, concurrent identity synchronization and full authorization matrix are not verified |

The historical acceptance standard and result files are retained as execution evidence. Their `passed` wording means the tests listed at that time passed; it does not mean the milestone is `ACCEPTED` under the V2.0 gate model.

## Rules from this review onward

1. Every result file must record Git commit, migration version, environment and exact commands.
2. A passing local test suite can only reach `IMPLEMENTED_LOCAL`.
3. Security and tenant slices require PostgreSQL plus real identity-provider verification.
4. `ACCEPTED` requires the signatures and Staging evidence defined in `../plans/里程碑后开发评审与验收计划.md`.
