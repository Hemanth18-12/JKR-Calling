import { campaignsApi, contactsApi } from "@jkr/sdk";
import { notFound } from "next/navigation";

import { CampaignDetail } from "@/components/campaign-detail";
import { getActiveWorkspaceContext } from "@/lib/session";

export default async function CampaignDetailPage({ params }: { params: { campaignId: string } }) {
  const { workspace, cookieHeader } = await getActiveWorkspaceContext();
  if (!workspace) notFound();

  const [campaign, campaignContacts, allContacts] = await Promise.all([
    campaignsApi.get(workspace.id, params.campaignId, { cookieHeader }),
    campaignsApi.listContacts(workspace.id, params.campaignId, { cookieHeader }),
    contactsApi.list(workspace.id, { cookieHeader }),
  ]);

  return (
    <div className="p-8">
      <CampaignDetail workspaceId={workspace.id} campaign={campaign} campaignContacts={campaignContacts} allContacts={allContacts} />
    </div>
  );
}
