import { contactsApi } from "@jkr/sdk";
import { notFound } from "next/navigation";

import { ContactsPage } from "@/components/contacts-page";
import { getActiveWorkspaceContext } from "@/lib/session";

export default async function ContactsRoutePage() {
  const { workspace, cookieHeader } = await getActiveWorkspaceContext();
  if (!workspace) notFound();

  const [contacts, suppressionEntries] = await Promise.all([
    contactsApi.list(workspace.id, { cookieHeader }),
    contactsApi.listSuppression(workspace.id, { cookieHeader }),
  ]);

  return (
    <div className="space-y-6 p-6">
      <div>
        <h1 className="text-xl font-semibold">Contacts</h1>
        <p className="text-sm text-muted-foreground">Leads and customers campaigns can call — subject to consent and suppression.</p>
      </div>
      <ContactsPage workspaceId={workspace.id} contacts={contacts} suppressionEntries={suppressionEntries} />
    </div>
  );
}
