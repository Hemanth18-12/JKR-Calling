import { notFound, redirect } from "next/navigation";
import { getActiveWorkspaceContext } from "@/lib/session";
import { CoinPaymentClient } from "@/components/coin-payment-client";

interface PayPageProps {
  searchParams: {
    tier?: string;
  };
}

export default async function CoinPaymentPage({ searchParams }: PayPageProps) {
  const { workspace } = await getActiveWorkspaceContext();
  if (!workspace) redirect("/login");

  return (
    <div className="p-4 sm:p-8 max-w-4xl mx-auto space-y-6">
      <CoinPaymentClient
        workspaceId={workspace.id}
        initialTierId={searchParams.tier || "tier_250"}
      />
    </div>
  );
}
