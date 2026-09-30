"use client";

import { APPOINTMENT_STATUS_VARIANT, type AppointmentOut } from "@jkr/contracts";
import { ApiClientError, operationsApi } from "@jkr/sdk";
import { Badge, Button, Card, CardContent, CardHeader, CardTitle, EmptyState, Input, Label, useToast } from "@jkr/ui";
import { Calendar, CalendarCheck2, Clock, Download, ExternalLink, FileSpreadsheet, Grid, List, Plus, ShieldCheck, User, X } from "lucide-react";
import { useRouter } from "next/navigation";
import * as React from "react";

export function AppointmentsList({ workspaceId, appointments }: { workspaceId: string; appointments: AppointmentOut[] }) {
  const router = useRouter();
  const { toast } = useToast();
  const [busyId, setBusyId] = React.useState<string | null>(null);
  const [viewMode, setViewMode] = React.useState<"list" | "calendar">("list");

  // Create appointment modal state
  const [isCreateOpen, setIsCreateOpen] = React.useState(false);
  const [customerName, setCustomerName] = React.useState("");
  const [customerPhone, setCustomerPhone] = React.useState("+91");
  const [appointmentDate, setAppointmentDate] = React.useState(new Date().toISOString().split("T")[0]);
  const [appointmentTime, setAppointmentTime] = React.useState("11:00");
  const [appointmentLocation, setAppointmentLocation] = React.useState("Aaha Dental Care, Road No. 12, Banjara Hills");
  const [appointmentNotes, setAppointmentNotes] = React.useState("General Consultation");
  const [submitting, setSubmitting] = React.useState(false);
  const [createError, setCreateError] = React.useState<string | null>(null);

  const handleCreateAppointment = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setCreateError(null);
    try {
      const scheduledIso = new Date(`${appointmentDate}T${appointmentTime}:00`).toISOString();
      await operationsApi.createAppointment(workspaceId, {
        customer_name: customerName,
        phone: customerPhone,
        scheduled_for: scheduledIso,
        location: appointmentLocation,
        notes: appointmentNotes,
        duration_minutes: 30,
      });
      toast({
        title: "Appointment Scheduled",
        description: "Appointment created with calendar invite and Google Calendar link.",
        variant: "success",
      });
      setIsCreateOpen(false);
      setCustomerName("");
      router.refresh();
    } catch (err) {
      setCreateError(err instanceof ApiClientError ? err.message : "Failed to schedule appointment.");
    } finally {
      setSubmitting(false);
    }
  };

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

  // Helper to extract Google Calendar URL from notes
  const getGoogleCalendarUrl = (notes?: string | null) => {
    if (!notes) return null;
    const match = notes.match(/https:\/\/calendar\.google\.com\/calendar\/[^\s\]]+/);
    return match ? match[0] : null;
  };

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

  // Client-side RFC 5545 .ics generator and downloader
  const downloadIcs = (apt: AppointmentOut) => {
    const dt = new Date(apt.scheduled_for);
    const pad = (n: number) => String(n).padStart(2, "0");
    const formatUtc = (d: Date) =>
      `${d.getUTCFullYear()}${pad(d.getUTCMonth() + 1)}${pad(d.getUTCDate())}T${pad(d.getUTCHours())}${pad(d.getUTCMinutes())}${pad(d.getUTCSeconds())}Z`;

    const dtStart = formatUtc(dt);
    const endDt = new Date(dt.getTime() + (apt.duration_minutes || 30) * 60000);
    const dtEnd = formatUtc(endDt);
    const dtStamp = formatUtc(new Date());
    const cleanSummary = (apt.contact_name ? `Appointment: ${apt.contact_name}` : "Consultation Appointment").replace(/[,;\\]/g, " ");
    const cleanDesc = (apt.notes || "Booked via JKR Calling AI Agent").replace(/[,;\\]/g, " ");
    const cleanLoc = (apt.location || "").replace(/[,;\\]/g, " ");

    const ics = [
      "BEGIN:VCALENDAR",
      "VERSION:2.0",
      "PRODID:-//JKR Calling//AI Voice Platform//EN",
      "CALSCALE:GREGORIAN",
      "METHOD:REQUEST",
      "BEGIN:VEVENT",
      `UID:apt-${apt.id}@jkr.ai`,
      `DTSTAMP:${dtStamp}`,
      `DTSTART:${dtStart}`,
      `DTEND:${dtEnd}`,
      `SUMMARY:${cleanSummary}`,
      `DESCRIPTION:${cleanDesc}`,
      ...(cleanLoc ? [`LOCATION:${cleanLoc}`] : []),
      "ORGANIZER;CN=JKR AI Calling:mailto:appointments@jkr.ai",
      "STATUS:CONFIRMED",
      "TRANSP:OPAQUE",
      "SEQUENCE:0",
      "BEGIN:VALARM",
      "ACTION:DISPLAY",
      "DESCRIPTION:Appointment Reminder",
      "TRIGGER:-PT30M",
      "END:VALARM",
      "END:VEVENT",
      "END:VCALENDAR",
    ].join("\r\n") + "\r\n";

    const blob = new Blob([ics], { type: "text/calendar;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `appointment-${apt.id.slice(0, 8)}.ics`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    toast({ title: "Calendar Invite Downloaded", description: `Saved as appointment-${apt.id.slice(0, 8)}.ics`, variant: "success" });
  };

  // Client-side CSV export
  const exportAppointmentsCsv = () => {
    if (sorted.length === 0) {
      toast({ title: "No appointments to export", variant: "danger" });
      return;
    }
    const headers = ["Appointment ID", "Customer Name", "Scheduled Date (IST)", "Scheduled Time (IST)", "Duration (Mins)", "Status", "Location", "Notes", "Created At"];
    const rows = sorted.map((a) => {
      const d = new Date(a.scheduled_for);
      const dateStr = d.toLocaleDateString("en-IN", { timeZone: "Asia/Kolkata" });
      const timeStr = d.toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata", hour: "2-digit", minute: "2-digit" });
      return [
        `"${a.id}"`,
        `"${(a.contact_name || "Customer").replace(/"/g, '""')}"`,
        `"${dateStr}"`,
        `"${timeStr}"`,
        a.duration_minutes || 30,
        `"${a.status}"`,
        `"${(a.location || "").replace(/"/g, '""')}"`,
        `"${(a.notes || "").replace(/[\r\n]+/g, " ").replace(/"/g, '""')}"`,
        `"${a.created_at}"`,
      ].join(",");
    });

    const csvContent = [headers.join(","), ...rows].join("\r\n");
    const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `appointments_export_${new Date().toISOString().split("T")[0]}.csv`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
    toast({ title: "CSV Exported", description: `Exported ${sorted.length} appointment(s) to CSV.`, variant: "success" });
  };

  return (
    <div className="space-y-4">
      {/* Top Bar: View Switcher, Create Button, CSV Export & Sync Status */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-surface border border-border p-3 rounded-xl">
        <div className="flex flex-wrap items-center gap-2">
          <Button
            size="sm"
            variant={viewMode === "list" ? "secondary" : "ghost"}
            className="text-xs h-8"
            onClick={() => setViewMode("list")}
          >
            <List className="h-3.5 w-3.5 mr-1" /> List View
          </Button>
          <Button
            size="sm"
            variant={viewMode === "calendar" ? "secondary" : "ghost"}
            className="text-xs h-8"
            onClick={() => setViewMode("calendar")}
          >
            <Grid className="h-3.5 w-3.5 mr-1" /> Calendar Grid
          </Button>
          <Button
            size="sm"
            className="text-xs h-8 ml-1"
            onClick={() => {
              setCreateError(null);
              setIsCreateOpen(true);
            }}
          >
            <Plus className="h-3.5 w-3.5 mr-1" /> Schedule Appointment
          </Button>
          <Button
            size="sm"
            variant="outline"
            className="text-xs h-8"
            onClick={exportAppointmentsCsv}
          >
            <Download className="h-3.5 w-3.5 mr-1" /> Export CSV
          </Button>
        </div>

        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <span className="flex items-center gap-1 text-emerald-400 font-medium">
            <ShieldCheck className="h-3.5 w-3.5" /> Conflict Protection
          </span>
          <span>·</span>
          <span className="flex items-center gap-1 text-primary">
            <Calendar className="h-3.5 w-3.5" /> Universal .ics & CSV Ready
          </span>
        </div>
      </div>

      {viewMode === "list" ? (
        <Card>
          <CardContent className="p-0">
            {sorted.length === 0 ? (
              <div className="p-6">
                <EmptyState
                  icon={Calendar}
                  title="No appointments scheduled yet"
                  description="Appointments are booked automatically by AI voice agents when caller confirms, or you can schedule one manually above."
                />
              </div>
            ) : (
              <div className="divide-y divide-border">
                {sorted.map((a) => {
                  const hasConflict = conflicts.has(a.id);
                  const gcalUrl = getGoogleCalendarUrl(a.notes);
                  return (
                    <div key={a.id} className="flex items-center justify-between px-5 py-3.5 text-sm hover:bg-surface-raised transition-colors">
                      <div className="flex items-center gap-3.5">
                        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary border border-primary/20">
                          <CalendarCheck2 className="h-4 w-4" />
                        </div>
                        <div>
                          <div className="flex items-center gap-2">
                            <p className="font-medium text-foreground">{a.contact_name || "Customer"}</p>
                            {hasConflict && (
                              <Badge variant="danger" className="text-[10px]">
                                Time Overlap Warning
                              </Badge>
                            )}
                            {gcalUrl && (
                              <a
                                href={gcalUrl}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="inline-flex items-center gap-1 text-[11px] text-blue-400 hover:underline bg-blue-500/10 px-2 py-0.5 rounded-md border border-blue-500/20"
                              >
                                <Calendar className="h-2.5 w-2.5" /> Google Calendar <ExternalLink className="h-2.5 w-2.5" />
                              </a>
                            )}
                          </div>
                          <p className="text-xs text-muted-foreground flex flex-wrap items-center gap-2 mt-0.5">
                            <span className="flex items-center gap-1 font-mono">
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
                            {a.location ? <span>· 📍 {a.location}</span> : null}
                            {a.notes ? <span className="italic">· {a.notes.replace(/\[Google Calendar:[^\]]+\]/, "")}</span> : null}
                          </p>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <Button
                          size="sm"
                          variant="outline"
                          className="h-7 text-xs text-primary hover:bg-primary/10 border-primary/30"
                          onClick={() => downloadIcs(a)}
                          title="Download standard .ics calendar invite for Google, Apple, and Outlook"
                        >
                          <Download className="h-3 w-3 mr-1" /> Calendar invite (.ics)
                        </Button>
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
            )}
          </CardContent>
        </Card>
      ) : (
        /* Calendar Grid View */
        sorted.length === 0 ? (
          <div className="space-y-4">
            <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-2.5">
              {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((day) => (
                <div key={day} className="rounded-xl border border-border/80 bg-surface/60 p-3.5 text-center">
                  <p className="text-xs font-semibold text-primary">{day}</p>
                  <p className="mt-2 text-[11px] text-muted-foreground/60">0 scheduled</p>
                </div>
              ))}
            </div>
            <EmptyState
              icon={Calendar}
              title="Calendar grid is clear"
              description="When agents schedule consultations, appointments, or follow-up calls, each slot appears dynamically in this calendar grid."
            />
          </div>
        ) : (
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
                    <div className="flex flex-col gap-1.5 pt-1">
                      <Button
                        size="sm"
                        variant="outline"
                        className="w-full text-xs h-7 text-primary hover:bg-primary/10 border-primary/30"
                        onClick={() => downloadIcs(a)}
                        title="Download standard .ics calendar invite for Google, Apple, and Outlook"
                      >
                        <Download className="h-3 w-3 mr-1" /> Calendar invite (.ics)
                      </Button>
                      {a.status === "scheduled" || a.status === "confirmed" ? (
                        <Button size="sm" variant="ghost" className="w-full text-xs h-7 text-danger hover:text-danger" onClick={() => cancel(a.id)}>
                          Cancel Booking
                        </Button>
                      ) : null}
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        )
      )}

      {/* Modal: Schedule Appointment */}
      {isCreateOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <Card className="w-full max-w-md border-border bg-surface shadow-2xl">
            <CardHeader className="flex flex-row items-center justify-between pb-3">
              <div>
                <CardTitle className="text-base font-semibold flex items-center gap-2">
                  <Calendar className="h-4 w-4 text-primary" /> Schedule Appointment
                </CardTitle>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Creates appointment and syncs to Google Calendar & Google Sheets.
                </p>
              </div>
              <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={() => setIsCreateOpen(false)}>
                <X className="h-4 w-4" />
              </Button>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleCreateAppointment} className="space-y-3.5">
                <div>
                  <Label htmlFor="apt-name" className="text-xs font-medium">Customer / Patient Name</Label>
                  <Input
                    id="apt-name"
                    placeholder="Gowtham Krishna"
                    value={customerName}
                    onChange={(e) => setCustomerName(e.target.value)}
                    required
                    className="mt-1"
                  />
                </div>
                <div>
                  <Label htmlFor="apt-phone" className="text-xs font-medium">Phone Number (E.164)</Label>
                  <Input
                    id="apt-phone"
                    placeholder="+919876543210"
                    value={customerPhone}
                    onChange={(e) => setCustomerPhone(e.target.value)}
                    required
                    className="mt-1"
                  />
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <Label htmlFor="apt-date" className="text-xs font-medium">Date</Label>
                    <Input
                      id="apt-date"
                      type="date"
                      value={appointmentDate}
                      onChange={(e) => setAppointmentDate(e.target.value)}
                      required
                      className="mt-1"
                    />
                  </div>
                  <div>
                    <Label htmlFor="apt-time" className="text-xs font-medium">Time</Label>
                    <Input
                      id="apt-time"
                      type="time"
                      value={appointmentTime}
                      onChange={(e) => setAppointmentTime(e.target.value)}
                      required
                      className="mt-1"
                    />
                  </div>
                </div>
                <div>
                  <Label htmlFor="apt-loc" className="text-xs font-medium">Location</Label>
                  <Input
                    id="apt-loc"
                    value={appointmentLocation}
                    onChange={(e) => setAppointmentLocation(e.target.value)}
                    className="mt-1"
                  />
                </div>
                <div>
                  <Label htmlFor="apt-notes" className="text-xs font-medium">Reason for Visit / Notes</Label>
                  <Input
                    id="apt-notes"
                    value={appointmentNotes}
                    onChange={(e) => setAppointmentNotes(e.target.value)}
                    className="mt-1"
                  />
                </div>
                {createError ? <p className="text-xs text-danger">{createError}</p> : null}
                <div className="flex justify-end gap-2 pt-2">
                  <Button type="button" variant="ghost" size="sm" onClick={() => setIsCreateOpen(false)}>
                    Cancel
                  </Button>
                  <Button type="submit" size="sm" loading={submitting}>
                    Schedule & Sync
                  </Button>
                </div>
              </form>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}

