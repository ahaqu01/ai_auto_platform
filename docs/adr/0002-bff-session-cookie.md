# ADR-0002: Browser authentication uses a BFF session cookie

Status: Accepted

The browser uses OIDC Authorization Code with PKCE through a same-origin BFF. The BFF holds Keycloak access and refresh tokens; the browser receives only an opaque HttpOnly, SameSite session cookie. Tokens must not be stored in LocalStorage or exposed to browser JavaScript.

All state-changing browser requests require Origin validation and a CSRF token bound to the server-side session. Logout revokes the Keycloak session and deletes the local session. Direct Bearer authentication remains available only for non-browser API clients under explicit scope.
