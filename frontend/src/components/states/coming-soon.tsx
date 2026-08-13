import type { ReactNode } from "react";
import { EmptyState } from "@/components/states/empty-state";

export function ComingSoon({ title, description }: { title: string; description: string }): ReactNode {
  return (
    <div className="p-6">
      <EmptyState icon="🚧" title={`${title} is coming soon`} description={description} />
    </div>
  );
}
