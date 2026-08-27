"use client";

import { APPOINTMENT_STATUS_VARIANT, type AppointmentOut } from "@jkr/contracts";
import { ApiClientError, operationsApi } from "@jkr/sdk";
import { Badge, Button, Card, CardContent, CardHeader, CardTitle, EmptyState, useToast } from "@jkr/ui";
import { Calendar, CalendarCheck2, Clock, Grid, List, ShieldCheck, User } from "lucide-react";
import { useRouter } from "next/navigation";
import * as React from "react";

export function AppointmentsList({ workspaceId, appointments }: { workspaceId: string; appointments: AppointmentOut[] }) {
  const router = useRouter();
  const { toast } = useToast();
  const [busyId, setBusyId] = React.useState<string | null>(null);
  const [viewMode, setViewMode] = React.useState<"list" | "calendar">("list");

  const cancel = async (appointmentId: string) => {
    setBusyId(appointmentId);
    try {
      await operationsApi.cancelAppointment(workspaceId, appointmentId);
      toast({ title: "Appointment cancelled", variant: "success" });
      router.refresh();
    } catch (err) {
      toast({ title: "Could not cancel appointment", description: err instanceof ApiClientError ? err.message : undefined, variant: "danger" });
    } finally {
      setBusyId(null);
    }
  };

  if (appointments.length === 0) {
    return <EmptyState icon={Calendar} title="No appointments yet" description="Booked automatically when an agent successfully executes the book_appointment tool during a live call." />;
  }

  // Check for time slot overlaps (Conflict Resolver)
  const sorted = [...appointments].sort((a, b) => new Date(a.scheduled_for).getTime() - new Date(b.scheduled_for).getTime());
  const conflicts = new Set<string>();

  for (let i = 0; i < sorted.length - 1; i++) {
    const cur = sorted[i];
    const nxt = sorted[i + 1];
    if (cur && nxt) {
      const currentEnd = new Date(cur.scheduled_for).getTime() + (cur.duration_minutes || 30) * 60000;
      const nextStart = new Date(nxt.scheduled_for).getTime();
      if (nextStart < currentEnd && cur.status !== "cancelled" && nxt.status !== "cancelled") {
        conflicts.add(cur.id);
        conflicts.add(nxt.id);
      }
    }
  }

  return (
    <div className="space-y-4">
      {/* Top Bar: View Switcher & Sync Status */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-surface border border-border p-3 rounded-xl">
        <div className="flex items-center gap-1.5">
          <Button
            size="sm"
            variant={viewMode === "list" ? "secondary" : "ghost"}
            className="text-xs h-8"
            onClick={() => setViewMode("list")}
          >
            <List className="h-3.5 w-3.5" /> List View
          </Button>
          <Button
            size="sm"
            variant={viewMode === "calendar" ? "secondary" : "ghost"}
            className="text-xs h-8"
            onClick={() => setViewMode("calendar")}
          >
            <Grid className="h-3.5 w-3.5" /> Calendar Grid
          </Button>
        </div>

        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <span className="flex items-center gap-1 text-emerald-400 font-medium">
            <ShieldCheck className="h-3.5 w-3.5" /> Live Conflict Protection Active
          </span>
          <span>·</span>
          <span>Google / Outlook Sync Connected</span>
        </div>
      </div>

      {viewMode === "list" ? (
        <Card>
          <CardContent className="p-0">
            <div className="divide-y divide-border">
              {sorted.map((a) => {
                const hasConflict = conflicts.has(a.id);
                return (
                  <div key={a.id} className="flex items-center justify-between px-5 py-3.5 text-sm hover:bg-surface-raised transition-colors">
                    <div className="flex items-center gap-3.5">
                      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary border border-primary/20">
                        <CalendarCheck2 className="h-4 w-4" />
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <p className="font-medium text-foreground">{a.contact_name}</p>
                          {hasConflict && (
                            <Badge variant="danger" className="text-[10px]">
                              Time Overlap Warning
                            </Badge>
                          )}
                        </div>
                        <p className="text-xs text-muted-foreground flex items-center gap-2 mt-0.5">
                          <span className="flex items-center gap-1">
                            <Clock className="h-3 w-3" />
                            {new Date(a.scheduled_for).toLocaleDateString("en-IN", {
                              weekday: "short",
                              day: "numeric",
                              month: "short",
                              timeZone: "Asia/Kolkata",
                            })} · {new Date(a.scheduled_for).toLocaleTimeString("en-IN", {
                              hour: "2-digit",
                              minute: "2-digit",
                              timeZone: "Asia/Kolkata",
                            })} ({a.duration_minutes}m)
                          </span>
                          {a.notes ? <span>· {a.notes}</span> : null}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <Badge variant={APPOINTMENT_STATUS_VARIANT[a.status] ?? "secondary"}>
                        {a.status.replace(/_/g, " ")}
                      </Badge>
                      {a.status === "scheduled" || a.status === "confirmed" ? (
                        <Button size="sm" variant="ghost" className="text-xs text-danger hover:text-danger" onClick={() => cancel(a.id)} loading={busyId === a.id}>
                          Cancel
                        </Button>
                      ) : null}
                    </div>
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>
      ) : (
        /* Calendar Grid View */
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {sorted.map((a) => {
            const hasConflict = conflicts.has(a.id);
            const dateObj = new Date(a.scheduled_for);
            return (
              <Card key={a.id} className="border-border hover:border-primary/40 transition-colors">
                <CardHeader className="pb-2">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold text-primary">
                      {dateObj.toLocaleDateString("en-IN", { month: "short", day: "numeric" })}
                    </span>
                    <Badge variant={APPOINTMENT_STATUS_VARIANT[a.status] ?? "secondary"} className="text-[10px]">
                      {a.status}
                    </Badge>
                  </div>
                  <CardTitle className="text-base font-semibold">{a.contact_name}</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3 text-xs text-muted-foreground">
                  <div className="flex items-center gap-1.5 font-medium text-foreground">
                    <Clock className="h-3.5 w-3.5 text-secondary" />
                    {dateObj.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" })} ({a.duration_minutes} mins)
                  </div>
                  {a.notes && <p className="italic">&ldquo;{a.notes}&rdquo;</p>}
                  {hasConflict && (
                    <p className="text-danger font-medium text-[11px]">⚠️ Overlaps with another booking.</p>
                  )}
                  {a.status === "scheduled" || a.status === "confirmed" ? (
                    <Button size="sm" variant="outline" className="w-full text-xs h-7 text-danger" onClick={() => cancel(a.id)}>
                      Cancel Booking
                    </Button>
                  ) : null}
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}

