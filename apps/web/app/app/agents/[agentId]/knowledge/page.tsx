import { knowledgeApi } from "@jkr/sdk";
import { Badge, Card, CardContent, CardDescription, CardHeader, CardTitle, EmptyState } from "@jkr/ui";
import { BookOpen } from "lucide-react";
import Link from "next/link";
import { notFound } from "next/navigation";

import { getActiveWorkspaceContext } from "@/lib/session";

export default async function AgentKnowledgeTabPage() {
  const { workspace, cookieHeader } = await getActiveWorkspaceContext();
  if (!workspace) notFound();

  const documents = await knowledgeApi.listDocuments(workspace.id, { cookieHeader });
  const approved = documents.filter((d) => d.approval_state === "approved");

  return (
    <div className="max-w-3xl space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Workspace knowledge</CardTitle>
          <CardDescription>
            Retrieval isn&apos;t scoped per agent in this pass — every agent in this workspace can draw from all approved
            documents below. Manage content from{" "}
            <Link href="/app/knowledge/documents" className="text-primary underline-offset-4 hover:underline">
              Knowledge
            </Link>
            .
          </CardDescription>
        </CardHeader>
        <CardContent>
          {approved.length === 0 ? (
            <EmptyState icon={BookOpen} title="No approved knowledge yet" description="Add and approve a document so this agent can answer from it during calls." />
          ) : (
            <ul className="divide-y divide-border">
              {approved.map((d) => (
                <li key={d.id} className="flex items-center justify-between py-2">
                  <span className="text-sm font-medium">{d.title}</span>
                  <div className="flex items-center gap-2">
                    <Badge variant="secondary">{d.source_type}</Badge>
                    <span className="text-xs text-muted-foreground">{d.chunk_count} chunks</span>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
