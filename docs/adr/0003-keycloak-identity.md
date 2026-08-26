# ADR-0003: Keycloak identity key and profile synchronization

Status: Accepted

Application identity is keyed by the immutable pair `(issuer, subject)`. Email is mutable profile data and never an identity key. The platform does not automatically merge users with equal email across subjects or issuers.

The first valid request atomically creates the application user. Later requests may synchronize verified email and display name. Issuer migration and account merge require an explicit audited administrative workflow. Passwords, MFA, verification and login failure policy remain exclusively in Keycloak.
