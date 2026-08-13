# MarketMind AI — User Guide (v1.0.0)

A tour of what MarketMind AI does, for a signed-in user. For installing
or deploying the application itself, see `docs/release/INSTALLATION_GUIDE.md`
or `docs/release/DEPLOYMENT_GUIDE.md`.

## Signing in

Sign in with your username/password at `/login`. Check "Remember me" to
stay signed in after closing the browser (stored in `localStorage`);
leave it unchecked for a session that ends when the tab closes
(`sessionStorage`). There is no self-service signup or password reset
in v1.0.0 — account provisioning is an administrator task
(`docs/release/ADMINISTRATOR_GUIDE.md`).

## Dashboard

The landing page after signing in. Shows your account summary,
connectivity status, quick links to every domain you have permission
for, live session activity (recommendations/alerts generated this
session), system health charts, and a recent-activity feed merging
real-time events with this session's own research runs. Click
"Customize dashboard" to reorder, resize, or hide cards — your layout
is saved automatically (locally, in your browser).

## Watchlists

Create and manage watchlists of companies. Add/remove companies, attach
notes per company, and see each watchlist's own portfolio summary
(sector/country/theme distribution, risk assessment status,
recommendation availability, intelligence commentary when configured).

## Research

Look up a company for an AI-generated research report — company
overview, confidence summary, sector/country exposure, evidence
supporting the analysis. Compare up to 2 reports side by side. Research
requires the backend to have an Anthropic API key configured; if it
doesn't, you'll see a clear "unavailable" state rather than a silent
failure.

## Screening

Build custom multi-criteria screens against the market (technical,
fundamental, sentiment, risk fields), save named screening profiles,
run them, and browse/search/compare results.

## Decision Center

The portfolio-centered workspace tying together recommendations,
strategy evaluation, risk analytics, signal detection, and alerts for a
selected watchlist. Recommendations and Risk auto-scope to your
selected portfolio; Strategy threads whichever recommendation you most
recently generated; Signals and Alerts are standalone tools (the
backend has no portfolio concept for either). Use `c` (see Keyboard
shortcuts below) to jump here directly.

## Historical Analysis

Run and review backtests (portfolio vs. benchmark performance,
drawdown curves, a timeline with recommendation markers from this
session), generate and browse AI explainability reports (why a
recommendation/strategy/risk assessment reached its conclusion,
including performance attribution), and compare backtests or
explainability reports side by side.

## Notifications

A real-time notification center — alerts, backtests, recommendations,
strategy evaluations, explainability completions, and system health
changes, delivered live over WebSocket as they happen on the backend.
Filter by domain, priority, or read/unread; search by title/summary.
The bell icon in the top navigation shows your unread count and a
preview of the most recent entries from anywhere in the app. Note:
history is session-only — the backend does not replay events that
happened before you connected, and a page refresh clears it.

## Settings

Personalize appearance (theme, accent color, density), tables (default
page size), charts (default data-label visibility), notifications
(toast duration, pinned behavior, sound, desktop notifications,
category filters), accessibility (reduced motion, high contrast, larger
text, focus highlight), and keyboard shortcuts (see below). Save named
"views" of your dashboard layout, chart defaults, or notification
filters to switch between them; export/import your entire settings as a
JSON file. Everything here is stored locally in your browser — nothing
is sent to or read from the backend.

## Keyboard shortcuts

Press `?` anywhere to see the full list. Defaults: `/` focuses the
current page's search box, `d`/`w`/`c`/`h`/`n`/`s` jump to
Dashboard/Watchlists/Decision Center/Historical Analysis/
Notifications/Settings (silently does nothing if you don't have
permission for that domain). Shortcuts never fire while you're typing
in a text field. Rebind any of them in Settings → Shortcuts.

## Offline and connection issues

A banner appears at the top of every page if your browser goes offline
or the real-time connection is unavailable/degraded — you don't need to
be on the dashboard to see it. If your session expires while you're
working, you're redirected immediately to a "session expired" page
rather than silently failing.

## What this application does not do

This is a market *intelligence* platform, not a trading one — there is
no live market data feed, no broker integration, and no order
execution anywhere in the app (`docs/release/KNOWN_LIMITATIONS.md`).
