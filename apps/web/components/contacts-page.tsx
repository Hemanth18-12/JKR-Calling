"use client";

import {
  CONSENT_PURPOSE_OPTIONS,
  CONSENT_SOURCE_OPTIONS,
  ContactCreate,
  SUPPRESSION_REASON_OPTIONS,
  SuppressionCreate,
  type ContactOut,
  type SuppressionOut,
} from "@jkr/contracts";
import { ApiClientError, contactsApi } from "@jkr/sdk";
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  FieldError,
  Input,
  Label,
  useToast,
} from "@jkr/ui";
import { zodResolver } from "@hookform/resolvers/zod";
import { ShieldOff, UserPlus } from "lucide-react";
import { useRouter } from "next/navigation";
import * as React from "react";
import { useForm } from "react-hook-form";

function NewContactForm({ workspaceId }: { workspaceId: string }) {
  const router = useRouter();
  const [formError, setFormError] = React.useState<string | null>(null);
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<ContactCreate>({ resolver: zodResolver(ContactCreate) });

  const onSubmit = async (data: ContactCreate) => {
    setFormError(null);
    try {
      await contactsApi.create(workspaceId, data);
      reset();
      router.refresh();
    } catch (err) {
      setFormError(err instanceof ApiClientError ? err.message : "Could not add contact.");
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Add contact</CardTitle>
        <CardDescription>Phone is normalized to E.164 and masked everywhere except unmasked-view.</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div>
            <Label htmlFor="contact-name">Full name</Label>
            <Input id="contact-name" placeholder="Ravi Kumar" {...register("full_name")} />
            <FieldError>{errors.full_name?.message}</FieldError>
          </div>
          <div>
            <Label htmlFor="contact-phone">Phone</Label>
            <Input id="contact-phone" placeholder="9876543210" {...register("phone")} />
            <FieldError>{errors.phone?.message}</FieldError>
          </div>
          <div>
            <Label htmlFor="contact-source">Lead source</Label>
            <Input id="contact-source" placeholder="website_form" {...register("lead_source")} />
          </div>
          {formError ? <p className="text-sm text-danger">{formError}</p> : null}
          <Button type="submit" className="w-full" loading={isSubmitting}>
            <UserPlus className="h-4 w-4" /> Add contact
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

function SuppressForm({ workspaceId }: { workspaceId: string }) {
  const router = useRouter();
  const { toast } = useToast();
  const [formError, setFormError] = React.useState<string | null>(null);
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<SuppressionCreate>({ resolver: zodResolver(SuppressionCreate), defaultValues: { reason: "customer_opt_out" } });

  const onSubmit = async (data: SuppressionCreate) => {
    setFormError(null);
    try {
      await contactsApi.suppress(workspaceId, data);
      toast({ title: "Number suppressed", description: "Takes effect immediately — no campaign can call it.", variant: "success" });
      reset({ reason: "customer_opt_out" });
      router.refresh();
    } catch (err) {
      setFormError(err instanceof ApiClientError ? err.message : "Could not suppress number.");
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Suppress a number</CardTitle>
        <CardDescription>Blocks every campaign, immediately and permanently until removed.</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div>
            <Label htmlFor="suppress-phone">Phone</Label>
            <Input id="suppress-phone" placeholder="9876543210" {...register("phone")} />
            <FieldError>{errors.phone?.message}</FieldError>
          </div>
          <div>
            <Label htmlFor="suppress-reason">Reason</Label>
            <select id="suppress-reason" className="flex h-10 w-full rounded-md border border-border bg-surface px-3 py-2 text-sm" {...register("reason")}>
              {SUPPRESSION_REASON_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </div>
          {formError ? <p className="text-sm text-danger">{formError}</p> : null}
          <Button type="submit" variant="destructive" className="w-full" loading={isSubmitting}>
            <ShieldOff className="h-4 w-4" /> Suppress
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

function ConsentRow({ workspaceId, contact }: { workspaceId: string; contact: ContactOut }) {
  const router = useRouter();
  const { toast } = useToast();
  const [open, setOpen] = React.useState(false);
  const [purpose, setPurpose] = React.useState("marketing");
  const [source, setSource] = React.useState("verbal_recorded");
  const [busy, setBusy] = React.useState(false);

  const submit = async () => {
    setBusy(true);
    try {
      await contactsApi.recordConsent(workspaceId, contact.id, { purpose: purpose as never, source: source as never });
      toast({ title: "Consent recorded", variant: "success" });
      setOpen(false);
      router.refresh();
    } catch (err) {
      toast({ title: "Could not record consent", description: err instanceof ApiClientError ? err.message : undefined, variant: "danger" });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="border-b border-border py-3 last:border-0">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-medium">{contact.full_name}</p>
          <p className="text-xs text-muted-foreground">{contact.phone_masked}{contact.lead_source ? ` · ${contact.lead_source}` : ""}</p>
        </div>
        <div className="flex items-center gap-2">
          {contact.is_suppressed ? <Badge variant="danger">suppressed</Badge> : null}
          <Badge variant={contact.consent_status === "granted" ? "success" : "secondary"}>{contact.consent_status}</Badge>
          <Button size="sm" variant="outline" onClick={() => setOpen((o) => !o)}>
            Record consent
          </Button>
        </div>
      </div>
      {open ? (
        <div className="mt-3 flex flex-wrap items-end gap-2 rounded-md border border-border bg-surface-raised p-3">
          <div>
            <Label htmlFor={`purpose-${contact.id}`}>Purpose</Label>
            <select id={`purpose-${contact.id}`} className="flex h-9 rounded-md border border-border bg-surface px-2 text-sm" value={purpose} onChange={(e) => setPurpose(e.target.value)}>
              {CONSENT_PURPOSE_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </div>
          <div>
            <Label htmlFor={`source-${contact.id}`}>Source</Label>
            <select id={`source-${contact.id}`} className="flex h-9 rounded-md border border-border bg-surface px-2 text-sm" value={source} onChange={(e) => setSource(e.target.value)}>
              {CONSENT_SOURCE_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </div>
          <Button size="sm" onClick={submit} loading={busy}>
            Save
          </Button>
        </div>
      ) : null}
    </div>
  );
}

export function ContactsPage({
  workspaceId,
  contacts,
  suppressionEntries,
}: {
  workspaceId: string;
  contacts: ContactOut[];
  suppressionEntries: SuppressionOut[];
}) {
  return (
    <div className="grid gap-6 lg:grid-cols-3">
      <Card className="lg:col-span-2">
        <CardHeader>
          <CardTitle>Contacts</CardTitle>
          <CardDescription>{contacts.length} contact{contacts.length === 1 ? "" : "s"}. Consent gates every campaign dispatch.</CardDescription>
        </CardHeader>
        <CardContent>
          {contacts.length === 0 ? (
            <p className="text-sm text-muted-foreground">No contacts yet — add your first one.</p>
          ) : (
            contacts.map((c) => <ConsentRow key={c.id} workspaceId={workspaceId} contact={c} />)
          )}
        </CardContent>
      </Card>
      <div className="space-y-6">
        <NewContactForm workspaceId={workspaceId} />
        <SuppressForm workspaceId={workspaceId} />
        {suppressionEntries.length > 0 ? (
          <Card>
            <CardHeader>
              <CardTitle>Suppression list</CardTitle>
              <CardDescription>{suppressionEntries.length} number{suppressionEntries.length === 1 ? "" : "s"} blocked.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-2">
              {suppressionEntries.map((s) => (
                <div key={s.id} className="flex items-center justify-between text-sm">
                  <span>{s.phone_masked}</span>
                  <Badge variant="danger">{s.reason.replace(/_/g, " ")}</Badge>
                </div>
              ))}
            </CardContent>
          </Card>
        ) : null}
      </div>
    </div>
  );
}
