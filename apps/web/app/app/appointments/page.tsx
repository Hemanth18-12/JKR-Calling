import { operationsApi } from "@jkr/sdk";
import { notFound } from "next/navigation";

import { AppointmentsList } from "@/components/appointments-list";
import { getActiveWorkspaceContext } from "@/lib/session";

export default async function AppointmentsPage() {
  const { workspace, cookieHeader } = await getActiveWorkspaceContext();
  if (!workspace) notFound();

  const appointments = await operationsApi.listAppointments(workspace.id, undefined, { cookieHeader });

  return (
    <div className="space-y-6 p-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Appointments</h1>
        <p className="text-muted-foreground">Booked by agents during calls via the book_appointment tool.</p>
      </div>
      <AppointmentsList workspaceId={workspace.id} appointments={appointments} />
    </div>
  );
}
