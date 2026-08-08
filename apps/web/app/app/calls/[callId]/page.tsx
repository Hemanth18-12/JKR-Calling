import { callsApi, toolsApi } from "@jkr/sdk";
import { notFound } from "next/navigation";

import { CallDetail } from "@/components/call-detail";
import { getActiveWorkspaceContext } from "@/lib/session";

export default async function CallDetailPage({ params }: { params: { callId: string } }) {
  const { workspace, cookieHeader } = await getActiveWorkspaceContext();
  if (!workspace) notFound();

  const [call, toolExecutions] = await Promise.all([
    callsApi.get(workspace.id, params.callId, { cookieHeader }),
    toolsApi.listExecutionsForCall(workspace.id, params.callId, { cookieHeader }),
  ]);

  return (
    <div className="p-8">
      <CallDetail call={call} toolExecutions={toolExecutions} />
    </div>
  );
}
