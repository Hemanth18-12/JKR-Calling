import { EmptyState } from "@jkr/ui";
import { Construction } from "lucide-react";

export function ComingSoon({ title, phase }: { title: string; phase: string }) {
  return (
    <div className="p-8">
      <h1 className="mb-6 text-2xl font-semibold tracking-tight">{title}</h1>
      <EmptyState
        icon={Construction}
        title="Not built in this pass yet"
        description={`${title} lands in ${phase}. See docs/IMPLEMENTATION_CHECKLIST.md for current status.`}
      />
    </div>
  );
}
