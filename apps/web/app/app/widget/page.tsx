import { agentsApi, coinsApi } from "@jkr/sdk";
import { notFound } from "next/navigation";

import { getActiveWorkspaceContext } from "@/lib/session";
import { WidgetStudio } from "./widget-studio";

export default async function WidgetStudioPage() {
  const { workspace, cookieHeader } = await getActiveWorkspaceContext();
  if (!workspace) notFound();

  const [agents, wallet] = await Promise.all([
    agentsApi.list(workspace.id, { cookieHeader }).catch(() => []),
    coinsApi.getWallet(workspace.id, { cookieHeader }).catch(() => null),
  ]);

  return (
    <div className="p-6 sm:p-8">
      <WidgetStudio
        workspaceId={workspace.id}
        agents={agents}
        walletCoins={wallet?.balance_coins ?? 0}
      />
    </div>
  );
}
