"use client";

import { APPOINTMENT_STATUS_VARIANT, type AppointmentOut } from "@jkr/contracts";
import { ApiClientError, operationsApi } from "@jkr/sdk";
import { Badge, Button, Card, CardContent, EmptyState, useToast } from "@jkr/ui";
import { Calendar } from "lucide-react";
import { useRouter } from "next/navigation";
import * as React from "react";

export function AppointmentsList({ workspaceId, appointments }: { workspaceId: string; appointments: AppointmentOut[] }) {
  const router = useRouter();
  const { toast } = useToast();
  const [busyId, setBusyId] = React.useState<string | null>(null);

  const cancel = async (appointmentId: string) => {
    setBusyId(appointmentId);
    try {
      await operationsApi.cancelAppointment(workspaceId, appointmentId);
      router.refresh();
    } catch (err) {
      toast({ title: "Could not cancel appointment", description: err instanceof ApiClientError ? err.message : undefined, variant: "danger" });
    } finally {
      setBusyId(null);
    }
  };

  if (appointments.length === 0) {
    return <EmptyState icon={Calendar} title="No appointments yet" description="Booked automatically when a book_appointment-objective call completes." />;
  }

  return (
    <Card>
      <CardContent className="p-0">
        <div className="divide-y divide-border">
          {appointments.map((a) => (
            <div key={a.id} className="flex items-center justify-between px-5 py-3 text-sm">
              <div>
                <p className="font-medium">{a.contact_name}</p>
                <p className="text-xs text-muted-foreground">
                  {new Date(a.scheduled_for).toLocaleString()} · {a.duration_minutes} min
                  {a.notes ? ` · ${a.notes}` : ""}
                </p>
              </div>
              <div className="flex items-center gap-2">
                <Badge variant={APPOINTMENT_STATUS_VARIANT[a.status] ?? "secondary"}>{a.status.replace(/_/g, " ")}</Badge>
                {a.status === "scheduled" || a.status === "confirmed" ? (
                  <Button size="sm" variant="ghost" onClick={() => cancel(a.id)} loading={busyId === a.id}>
                    Cancel
                  </Button>
                ) : null}
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
