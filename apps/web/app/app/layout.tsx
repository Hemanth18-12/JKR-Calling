import { workspacesApi } from "@jkr/sdk";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { AppShell } from "@/components/app-shell";
import { getServerSession } from "@/lib/session";

export default async function AuthenticatedLayout({ children }: { children: React.ReactNode }) {
  const me = await getServerSession();
  if (!me) redirect("/login");

  const cookieHeader = cookies().toString();
  const workspaces = await workspacesApi.list({ cookieHeader }).catch(() => []);

  return (
    <AppShell me={me} workspaces={workspaces} activeWorkspaceId={me.active_workspace_id}>
      {children}
    </AppShell>
  );
}
