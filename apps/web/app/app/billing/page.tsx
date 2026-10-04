import { billingApi, coinsApi } from "@jkr/sdk";
import { notFound } from "next/navigation";

import { CoinsWallet } from "@/components/coins-wallet";
import { UsageSummaryView } from "@/components/usage-summary";
import { getActiveWorkspaceContext } from "@/lib/session";

export default async function BillingPage() {
  const { workspace, cookieHeader } = await getActiveWorkspaceContext();
  if (!workspace) notFound();

  const [usage, wallet, requests, transactions] = await Promise.all([
    billingApi.usage(workspace.id, { cookieHeader }),
    coinsApi.getWallet(workspace.id, { cookieHeader }),
    coinsApi.getTopupRequests(workspace.id, { cookieHeader }),
    coinsApi.getTransactions(workspace.id, { cookieHeader }),
  ]);

  return (
    <div className="space-y-8 p-6 sm:p-8">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-foreground">Coin Wallet &amp; Billing</h1>
        <p className="text-sm text-muted-foreground">
          Top up AI calling coins via UPI QR payment, track usage deductions, and monitor campaign telemetry.
        </p>
      </div>

      {/* Part 1 & 2: Coin Wallet, QR Payment, and Transactions */}
      <CoinsWallet
        workspaceId={workspace.id}
        initialWallet={wallet}
        initialRequests={requests}
        initialTransactions={transactions}
      />

      <div className="border-t border-border/80 pt-6">
        <h2 className="text-lg font-semibold tracking-tight text-foreground mb-4">
          Telemetry &amp; Provider Metrics
        </h2>
        <UsageSummaryView usage={usage} />
      </div>
    </div>
  );
}
