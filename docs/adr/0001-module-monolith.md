# ADR-0001: Modular monolith for Phase 1

Status: Accepted

The control plane is deployed as one FastAPI process with strict module boundaries. PostgreSQL is the business source of truth. Temporal manages durable execution. Modules may call another module's application interface, never another module's repository directly.

