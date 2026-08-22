import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type * as ReactRouterModule from "@tanstack/react-router";
import { NotificationCenterPage } from "@/features/notifications/notification-center-page";
import { useRealtimeNotificationStore, type NotificationCenterEntry } from "@/store/realtime-notification-store";
import { useNotificationFilterStore } from "@/store/notification-filter-store";

vi.mock("@tanstack/react-router", async () => {
  const actual = await vi.importActual<typeof ReactRouterModule>("@tanstack/react-router");
  return {
    ...actual,
    Link: (props: { to: string; params?: Record<string, string>; children?: ReactNode; onClick?: () => void }) => {
      const href = props.params
        ? Object.entries(props.params).reduce((path, [key, value]) => path.replace(`$${key}`, value), props.to)
        : props.to;
      return (
        <a href={href} onClick={props.onClick}>
          {props.children}
        </a>
      );
    },
  };
});

const NOW = "2026-01-15T12:00:00Z";

function buildEntry(overrides: Partial<NotificationCenterEntry> = {}): NotificationCenterEntry {
  return {
    id: `entry-${String(Math.random())}`,
    eventType: "ALERT_GENERATED",
    domain: "alerts",
    priority: "HIGH",
    title: "New HIGH alert — AAPL",
    summary: "RSI oversold.",
    occurredAt: NOW,
    read: false,
    entityRef: { kind: "alert" },
    ...overrides,
  };
}

describe("NotificationCenterPage", () => {
  beforeEach(() => {
    vi.setSystemTime(new Date(NOW));
    useRealtimeNotificationStore.setState({ entries: [] });
    useNotificationFilterStore.getState().resetFilters();
  });

  it("shows an empty state when there are no notifications at all", () => {
    render(<NotificationCenterPage />);
    expect(screen.getByText("No notifications yet this session")).toBeInTheDocument();
  });

  it("renders entries grouped by date, with a deep link for backtest entries and a plain button for alert entries", () => {
    useRealtimeNotificationStore.setState({
      entries: [
        buildEntry({ id: "a", title: "New HIGH alert — AAPL", entityRef: { kind: "alert" } }),
        buildEntry({
          id: "b",
          domain: "backtests",
          eventType: "BACKTEST_COMPLETED",
          title: "Backtest complete",
          entityRef: { kind: "backtest", runId: "run-1" },
        }),
      ],
    });

    render(<NotificationCenterPage />);

    expect(screen.getByText("Today")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Backtest complete/ })).toHaveAttribute("href", "/historical-analysis/backtests/run-1");
    expect(screen.getByRole("button", { name: /New HIGH alert/ })).toBeInTheDocument();
  });

  it("filters by domain", async () => {
    useRealtimeNotificationStore.setState({
      entries: [buildEntry({ id: "a", domain: "alerts", title: "Alert entry" }), buildEntry({ id: "b", domain: "health", title: "Health entry", entityRef: { kind: "health" } })],
    });
    const user = userEvent.setup();
    render(<NotificationCenterPage />);

    // All domains start checked (no filter) — unchecking every domain
    // except "Health" isolates it.
    await user.click(screen.getByLabelText("Alerts"));
    await user.click(screen.getByLabelText("Backtests"));
    await user.click(screen.getByLabelText("Recommendations"));
    await user.click(screen.getByLabelText("Strategy"));
    await user.click(screen.getByLabelText("Explainability"));

    expect(screen.queryByText("Alert entry")).not.toBeInTheDocument();
    expect(screen.getByText("Health entry")).toBeInTheDocument();
  });

  it("filters by read status", async () => {
    useRealtimeNotificationStore.setState({
      entries: [buildEntry({ id: "a", title: "Unread entry", read: false }), buildEntry({ id: "b", title: "Read entry", read: true })],
    });
    const user = userEvent.setup();
    render(<NotificationCenterPage />);

    await user.selectOptions(screen.getByLabelText("Filter by read status"), "unread");

    expect(screen.getByText("Unread entry")).toBeInTheDocument();
    expect(screen.queryByText("Read entry")).not.toBeInTheDocument();
  });

  it("searches by title/summary text", async () => {
    useRealtimeNotificationStore.setState({
      entries: [buildEntry({ id: "a", title: "New HIGH alert — AAPL" }), buildEntry({ id: "b", title: "New HIGH alert — MSFT" })],
    });
    const user = userEvent.setup();
    render(<NotificationCenterPage />);

    await user.type(screen.getByLabelText("Search notifications"), "MSFT");

    expect(screen.queryByText("New HIGH alert — AAPL")).not.toBeInTheDocument();
    expect(screen.getByText("New HIGH alert — MSFT")).toBeInTheDocument();
  });

  it("shows the no-matches empty state when filters exclude everything", async () => {
    useRealtimeNotificationStore.setState({ entries: [buildEntry({ domain: "alerts" })] });
    const user = userEvent.setup();
    render(<NotificationCenterPage />);

    await user.click(screen.getByLabelText("Alerts"));

    expect(screen.getByText("No notifications match your filters")).toBeInTheDocument();
  });

  it("deep-links a portfolio-scoped market/news/decision entry to /decisions/$portfolioId", () => {
    useRealtimeNotificationStore.setState({
      entries: [
        buildEntry({
          id: "a", domain: "market", eventType: "SIGNIFICANT_MARKET_CHANGE", title: "Dell moved 5%",
          entityRef: { kind: "market", portfolioId: "wl-1" },
        }),
      ],
    });

    render(<NotificationCenterPage />);

    expect(screen.getByRole("link", { name: /Dell moved 5%/ })).toHaveAttribute("href", "/decisions/wl-1");
  });

  it("renders a portfolio-agnostic market/news/decision entry as a plain button, not a broken link", () => {
    useRealtimeNotificationStore.setState({
      entries: [
        buildEntry({
          id: "a", domain: "news", eventType: "SIGNIFICANT_NEWS_UPDATE", title: "New evidence for Dell",
          entityRef: { kind: "news", portfolioId: null },
        }),
      ],
    });

    render(<NotificationCenterPage />);

    expect(screen.queryByRole("link", { name: /New evidence for Dell/ })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /New evidence for Dell/ })).toBeInTheDocument();
  });

  it("v1.2 Priority 3: deep-links a digest entry to /decisions/$portfolioId and lists each contained change", () => {
    useRealtimeNotificationStore.setState({
      entries: [
        buildEntry({
          id: "digest-1", domain: "decisions", eventType: "PORTFOLIO_INTELLIGENCE_CHANGED",
          title: "2 decision changes affecting Portfolio A",
          summary: "Risk: LOW → HIGH; Recommendation: HOLD → BUY",
          entityRef: { kind: "decision", portfolioId: "wl-1" },
          digest: {
            portfolioId: "wl-1",
            windowStart: NOW,
            windowMs: 5 * 60 * 1000,
            changes: [
              { eventFingerprint: "fp1", domain: "RISK", label: "Portfolio A", previousValue: "LOW", currentValue: "HIGH", priority: "HIGH", summary: "x", occurredAt: NOW },
              { eventFingerprint: "fp2", domain: "RECOMMENDATION", label: "AAPL", previousValue: "HOLD", currentValue: "BUY", priority: "MEDIUM", summary: "y", occurredAt: NOW },
            ],
          },
        }),
      ],
    });

    render(<NotificationCenterPage />);

    expect(screen.getByRole("link", { name: /2 decision changes affecting Portfolio A/ })).toHaveAttribute("href", "/decisions/wl-1");
    expect(screen.getByText("Risk: LOW → HIGH")).toBeInTheDocument();
    expect(screen.getByText("Recommendation: HOLD → BUY")).toBeInTheDocument();
  });

  it("includes Market/News/Decisions in the domain filter and filters by them", async () => {
    useRealtimeNotificationStore.setState({
      entries: [
        buildEntry({ id: "a", domain: "decisions", eventType: "PORTFOLIO_INTELLIGENCE_CHANGED", title: "Risk changed", entityRef: { kind: "decision", portfolioId: "wl-1" } }),
        buildEntry({ id: "b", domain: "alerts", title: "Alert entry" }),
      ],
    });
    const user = userEvent.setup();
    render(<NotificationCenterPage />);

    expect(screen.getByLabelText("Market")).toBeInTheDocument();
    expect(screen.getByLabelText("News")).toBeInTheDocument();
    expect(screen.getByLabelText("Decisions")).toBeInTheDocument();

    await user.click(screen.getByLabelText("Alerts"));

    expect(screen.queryByText("Alert entry")).not.toBeInTheDocument();
    expect(screen.getByText("Risk changed")).toBeInTheDocument();
  });

  it("marks an entry read on click", async () => {
    useRealtimeNotificationStore.setState({ entries: [buildEntry({ id: "a", title: "Click me", read: false })] });
    const user = userEvent.setup();
    render(<NotificationCenterPage />);

    await user.click(screen.getByRole("button", { name: /Click me/ }));

    expect(useRealtimeNotificationStore.getState().entries[0]?.read).toBe(true);
  });

  it("clear empties the list", async () => {
    useRealtimeNotificationStore.setState({ entries: [buildEntry()] });
    const user = userEvent.setup();
    render(<NotificationCenterPage />);

    await user.click(screen.getByRole("button", { name: "Clear" }));

    expect(useRealtimeNotificationStore.getState().entries).toEqual([]);
  });
});
