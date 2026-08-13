import type { ReactNode } from "react";
import { WeightedBarList } from "@/components/weighted-bar-list";
import type { PortfolioExposure } from "@/types/portfolio";

/** Exactly one of `sector`/`country`/`industry` is populated per entry
 * (`app/risk/models.py`'s own `PortfolioExposure`) — split into the
 * three dimensions the spec asks for. `weight` is a 0-1 fraction of
 * portfolio holdings (`count / total`, `app/risk/engine.py`), shown as
 * a percentage. */
export function RiskExposurePanel({ exposures }: { exposures: PortfolioExposure[] }): ReactNode {
  const sectors = exposures.filter((e) => e.sector !== null).map((e) => ({ label: e.sector ?? "", weight: e.weight }));
  const countries = exposures.filter((e) => e.country !== null).map((e) => ({ label: e.country ?? "", weight: e.weight }));
  const industries = exposures.filter((e) => e.industry !== null).map((e) => ({ label: e.industry ?? "", weight: e.weight }));

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
      <WeightedBarList title="Sector exposure" items={sectors} emptyMessage="No sector exposure data." valueFormat="percent" />
      <WeightedBarList title="Country exposure" items={countries} emptyMessage="No country exposure data." valueFormat="percent" />
      <WeightedBarList title="Industry exposure" items={industries} emptyMessage="No industry exposure data." valueFormat="percent" />
    </div>
  );
}
