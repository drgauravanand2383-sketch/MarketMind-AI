"""Authentication & Authorization Framework: provider-agnostic
authentication (JWT is the first provider), RBAC authorization with role
hierarchy, and reusable, HTTP-independent policies.

Independent from the API layer — `app/api/` consumes
`AuthenticationService`/`AuthorizationService`/`PolicyEvaluator` through
`app.auth.dependencies`, never the other way around. No business logic
from any domain engine (Screening through Explainability) is modified or
referenced anywhere in this package.

No broker authentication, no OAuth providers, no social login, no SSO, no
billing, and no multi-tenancy exist anywhere in this package.
"""
