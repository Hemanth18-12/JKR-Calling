import { knowledgeApi } from "@jkr/sdk";
import { notFound } from "next/navigation";

import { KnowledgeDocuments } from "@/components/knowledge-documents";
import { getActiveWorkspaceContext } from "@/lib/session";

export default async function KnowledgeDocumentsPage() {
  const { workspace, cookieHeader } = await getActiveWorkspaceContext();
  if (!workspace) notFound();

  const documents = await knowledgeApi.listDocuments(workspace.id, { cookieHeader });

  return (
    <div className="space-y-6 p-6">
      <div>
        <h1 className="text-xl font-semibold">Knowledge</h1>
        <p className="text-sm text-muted-foreground">
          Content agents can draw from during calls. Everything needs review before it&apos;s used in a live conversation.
        </p>
      </div>
      <KnowledgeDocuments workspaceId={workspace.id} documents={documents} />
    </div>
  );
}
