# MarketMind AI — Real-Time Event & WebSocket Framework (`/ws`)

Produced by Sprint 59, Phase 2. Delivers already-completed backend
activity (alerts, backtests, recommendations, strategy evaluations, risk
assessments, explainability, health) to authenticated clients in real
time over a single WebSocket connection. Read
`docs/architecture/AUTHENTICATION_ARCHITECTURE.md` and
`docs/architecture/INTELLIGENCE_API.md` first — this document only
covers what Sprint 59 adds on top.

**No new business logic.** Every event carries an already-computed
domain result (`Alert`, `RecommendationResult`, `BacktestResult`, ...)
straight through; nothing in `app/api/ws/` scores, evaluates, or
recomputes anything. Publishing is triggered synchronously from the
existing REST routers, right after their existing service call succeeds
— never from a background job, a timer, or a new orchestration layer.

## 1. Architecture

```
app/api/ws/
  router.py                The one /ws route — connect, auth, message loop
  connection_manager/
    connection.py            WebSocketConnection — plain per-connection state
    manager.py                ConnectionManager — connect/disconnect/heartbeat/
                                subscribe/unsubscribe/broadcast/targeted delivery
  event_models/
    event_type.py             EventType enum (8 supported event types)
    base.py                    BaseEvent[payload], EventMetadata
    events.py                  AlertEvent, RecommendationEvent, BacktestEvent,
                                StrategyEvent, RiskEvent, ExplainabilityEvent,
                                HealthEvent, EventEnvelope
  publishers/
    event_publisher.py        EventPublisher — one publish_* method per event
                                type; wraps an already-computed result, broadcasts
  subscriptions/
    models.py                  Subscription, SubscribeMessage, UnsubscribeMessage
    registry.py                 SubscriptionRegistry — per-connection filter matching
  dependencies/
    auth.py                     authenticate_websocket (reuses AuthenticationService)
    permissions.py               EventType -> required permission string mapping
    services.py                  Dependency providers (app.state resolution)
```

`ConnectionManager` and `EventPublisher` are constructed once in
`app/main.py`'s `create_app()` — not `app/bootstrap.py` — since they hold
no external connections and construct nothing business-related, exactly
like Sprint 58's `InMemoryResultStore`s. Both are attached to
`app.state.connection_manager` / `app.state.event_publisher`.

## 2. Connection lifecycle

1. Client opens `GET /ws` (upgraded to a WebSocket) with a bearer token.
2. `authenticate_websocket()` resolves a principal via
   `AuthenticationService.validate()` — the exact method
   `AuthenticationMiddleware` already calls for HTTP requests (Starlette's
   `BaseHTTPMiddleware` never runs for a `websocket` ASGI scope, so this
   is done by hand, once, at connect time). No token, an invalid token, or
   an unconfigured framework closes the socket immediately (`1008`
   Policy Violation for auth failure, `1011` Internal Error if
   `connection_manager`/`policy_evaluator` aren't configured) — the
   socket is never left open unauthenticated.
3. `ConnectionManager.connect()` accepts the socket, generates a
   `connection_id`, and registers `WebSocketConnection(connection_id,
   websocket, principal, connected_at, last_heartbeat_at)`.
4. The server sends `{"type": "connected", "connection_id": "..."}`.
5. The server then loops on `receive_text()`, dispatching each inbound
   message (`subscribe`/`unsubscribe`/`ping`) — see §5.
6. On client disconnect (or any unrecoverable transport error),
   `ConnectionManager.disconnect()` removes the connection and every
   subscription it held — always run from a `finally` block, so cleanup
   happens on every exit path.
7. If a `send` to a connection ever fails (the client is gone but the
   server hasn't noticed yet), `ConnectionManager` catches the exception,
   logs it, and disconnects that connection immediately rather than
   letting a broadcast loop fail or leaving a zombie registry entry.

## 3. Authentication & authorization

**Authentication** (`app.api.ws.dependencies.auth.authenticate_websocket`):
reuses `AuthenticationService.validate(token)` — no token verification
logic is duplicated. The token is read from the `Authorization: Bearer
<token>` header if present, else a `?token=` query parameter (browsers'
native WebSocket API cannot set custom headers on the handshake, so a
query parameter is the conventional fallback every WS framework supports).

**Authorization**: subscribing to an event type requires the same
permission string its equivalent REST resource already requires —
`app.api.ws.dependencies.permissions.required_permission_for()`:

| Event type | Required permission |
|---|---|
| `ALERT_GENERATED` | `alerts:read` |
| `BACKTEST_STARTED` / `BACKTEST_COMPLETED` | `backtest:read` |
| `RECOMMENDATION_GENERATED` | `portfolio:read` |
| `STRATEGY_EVALUATION_COMPLETED` | `strategy:read` |
| `RISK_ASSESSMENT_COMPLETED` | `portfolio:read` |
| `EXPLAINABILITY_COMPLETED` | `explainability:read` |
| `HEALTH_STATUS_CHANGED` | *(none — authentication alone is sufficient)* |

Checked via the existing `PolicyEvaluator.evaluate(RequirePermission(...), principal)`
— the exact same policy objects `require_policy` uses for REST endpoints,
just invoked by hand inside the message handler instead of a FastAPI
`Depends()` (WebSocket message-level authorization has no per-message
dependency-injection equivalent to a route's `dependencies=[...]`). No
inline role/permission check exists anywhere — only this one
`event_type -> permission string` lookup table plus the existing evaluator.

A `user_id`/`role` is never accepted from the client — see §4.

## 4. Subscription model

Inbound `{"action": "subscribe", "event_types": [...], "correlation_id": "..."}`:

- `event_types`: which event types to receive. **Empty means every event
  type** — and authorizes against every type's required permission, so a
  broad subscription needs broad read access.
- `correlation_id`: optional filter — only events sharing this id are
  delivered (e.g. subscribe with `correlation_id="<backtest run id>"` to
  watch one specific run's `BACKTEST_STARTED`/`BACKTEST_COMPLETED` pair
  and nothing else).

A **duplicate** `subscribe` (identical `event_types`+`correlation_id`
already active) is detected and reported as `{"type":
"duplicate_subscription", ...}` rather than silently accepted twice.

`{"action": "unsubscribe", ...}` removes a matching active subscription
(`{"type": "unsubscribed", ...}`) or reports `{"type": "not_subscribed",
...}` if it wasn't active.

**By user / by role** (the other two axes the spec asks for) are **not**
client-subscribable fields — a client can only ever receive events
addressed to *its own* authenticated principal. This is deliberate: a
`user_id`/`role` field on a subscribe message would let a client ask to
receive another user's events, which is a privilege-escalation bug, not
a subscription feature. Instead, `ConnectionManager.send_to_user(user_id,
event)` / `.send_to_role(role, event)` are server-side *targeted delivery*
primitives (bypassing subscription filters entirely) — tested directly in
`tests/api/ws/test_connection_manager.py` — available for a future sprint
to call when a use case needs to address one specific user/role rather
than broadcast to every matching subscriber.

## 5. Message format

Every message — both directions — is a single JSON text frame.

**Inbound** (client -> server):
```json
{"action": "subscribe", "event_types": ["ALERT_GENERATED"], "correlation_id": null}
{"action": "unsubscribe", "event_types": ["ALERT_GENERATED"]}
{"action": "ping"}
```

**Outbound** (server -> client) — every message has a `"type"` field:

| `type` | When |
|---|---|
| `connected` | Once, right after a successful handshake — carries `connection_id` |
| `subscribed` / `duplicate_subscription` | Response to `subscribe` |
| `unsubscribed` / `not_subscribed` | Response to `unsubscribe` |
| `pong` | Response to `ping` |
| `error` | Malformed JSON, missing/unknown `action`, invalid subscription payload, or forbidden subscription — see §6 |
| `event` | An `EventEnvelope` — an actual real-time event delivery |

```json
// event delivery
{
  "type": "event",
  "metadata": { "connection_id": "...", "delivered_at": "2026-08-08T00:00:00Z" },
  "event": {
    "event_id": "...", "event_type": "ALERT_GENERATED",
    "timestamp": "2026-08-08T00:00:00Z", "correlation_id": "<alert id>",
    "payload": { /* the full Alert object, unmodified */ }
  }
}
```

## 6. Reliability & validation

A malformed message, unknown action, or invalid/forbidden subscription
**never closes the connection** — it gets an `error`/
`duplicate_subscription` response and the socket stays open and usable
(verified directly: `tests/api/ws/test_router.py::test_malformed_json_does_not_close_the_connection`
sends garbage, gets an error, then successfully pings on the same
connection). Only a failed handshake (unauthenticated, or the framework
isn't configured) or a genuine client disconnect ends the connection.

| Failure | Response |
|---|---|
| Not valid JSON | `{"type": "error", "code": "malformed_message"}` |
| Missing/unknown `action` | `{"type": "error", "code": "unknown_action"}` |
| Invalid `subscribe`/`unsubscribe` payload (e.g. an unknown event type string) | `{"type": "error", "code": "invalid_subscription"}` |
| Subscribing without the required permission | `{"type": "error", "code": "forbidden"}` |
| An unexpected exception while handling one message | `{"type": "error", "code": "internal_error"}` — logged, connection stays open |

**No message persistence, no replay** — a client that connects after an
event was published simply never sees it; there is no buffer, queue, or
history. This is explicit in the sprint's own constraints.

## 7. Heartbeat protocol

Client-driven ping/pong: the client sends `{"action": "ping"}` at
whatever interval it chooses; the server responds `{"type": "pong"}` and
records the heartbeat (`ConnectionManager.heartbeat()` updates
`WebSocketConnection.last_heartbeat_at`). There is no server-initiated
timer — a periodic server-side ping would need a background task per
connection, which this sprint's constraints rule out (no background
jobs). `last_heartbeat_at` is tracked for a future sprint to use for
idle-connection cleanup if needed; nothing currently reads it back.

## 8. Supported event types & their REST trigger points

| Event type | Publishing router | Correlation id |
|---|---|---|
| `ALERT_GENERATED` | `POST /api/v1/alerts/evaluate` (once per newly `GENERATED` alert) | `Alert.id` |
| `BACKTEST_STARTED` | `POST /api/v1/backtests` (before `run_backtest()`, a synthetic `PENDING` `BacktestRun`) | `BacktestRequest.id` |
| `BACKTEST_COMPLETED` | `POST /api/v1/backtests` (after `run_backtest()` returns) | `BacktestRequest.id` (same as started) |
| `RECOMMENDATION_GENERATED` | `POST /api/v1/portfolio/recommendations` | `RecommendationResult.request_id` |
| `STRATEGY_EVALUATION_COMPLETED` | `POST /api/v1/strategies/evaluate` | `StrategyEvaluationResult.request_id` |
| `EXPLAINABILITY_COMPLETED` | `POST /api/v1/explainability` | `ExplainabilityResult.request_id` |
| `HEALTH_STATUS_CHANGED` | `GET /api/v1/health` (only when `state` differs from the previous call — tracked in `app.state.last_health_state`) | none |
| `RISK_ASSESSMENT_COMPLETED` | **none — known gap, see below** | `RiskAssessment.request_id` |

**Known gap:** no REST endpoint anywhere calls
`RiskAnalyticsService.assess_portfolio()` — Sprint 57 designed
`GET /portfolio/risk` as a read-only lookup of an already-stored
assessment, and this sprint's own constraint ("REST API surface is
feature complete") rules out adding a creation endpoint to fix that. The
`RiskEvent` model and `EventPublisher.publish_risk_assessment_completed()`
both exist and are fully tested
(`tests/api/ws/test_event_publisher.py::test_publish_risk_assessment_completed`)
— ready for whichever future sprint adds that REST capability.

`BACKTEST_STARTED`'s payload is a `BacktestRun` the router constructs
itself (`request_id`, current timestamp, `status=PENDING`) — the real
`BacktestingService.run_backtest()` computes and persists the run and
result together in one call, so there is no genuine intermediate
"running" `BacktestRun` to fetch; the started event announces the
attempt honestly without inventing any new computation.

## 9. Future distributed event bus integration

This sprint's constraints explicitly rule out Kafka, RabbitMQ, Redis
Streams, or any distributed messaging system — `ConnectionManager` is a
single-process, in-memory registry, and `EventPublisher.broadcast()`
only ever reaches connections held by the same application instance. This
means:

- **Does not scale past one process.** Running multiple app instances
  behind a load balancer means a client connected to instance A never
  sees an event published by instance B.
- **No delivery guarantee.** A connection that's briefly disconnected
  (or an instance that restarts) loses events published during that gap
  — there is no queue, no replay, no persistence (§6).

A future sprint introducing a distributed event bus should:

1. Keep `EventPublisher`'s public interface (`publish_alert_generated`,
   etc.) unchanged — routers already call it and shouldn't need to
   change again.
2. Change only `EventPublisher`'s internals to publish onto the
   distributed bus instead of (or in addition to) calling
   `ConnectionManager.broadcast()` directly.
3. Add a bus-consumer component per app instance that receives events
   from the bus and calls the *same* `ConnectionManager.broadcast()`
   this sprint already built — `ConnectionManager`'s connection/
   subscription-matching logic does not need to change at all, only
   *what feeds it* changes.

## 10. Testing

`tests/api/ws/` — `test_connection_manager.py` (17 tests: lifecycle,
heartbeat, subscribe/duplicate, broadcast, targeted delivery, send-failure
cleanup, concurrent connections), `test_subscription_registry.py` (9
tests: matching by event type/correlation id), `test_event_models.py` (8
tests: construction, `extra="forbid"`, envelope round-tripping),
`test_event_publisher.py` (8 tests: one per `publish_*` method),
`test_router.py` (18 end-to-end tests over a real
`TestClient.websocket_connect`: auth reject/accept, subscribe/unsubscribe/
duplicate/forbidden, ping/pong, malformed/unknown messages, broadcast,
targeted delivery, concurrent connections, disconnect cleanup),
`test_rest_integration.py` (6 tests proving the actual REST-router wiring
end-to-end: hitting a real REST endpoint delivers a real event to a
subscribed WebSocket connection). 66 new tests total, zero regressions
across the full suite (2697 passed).
