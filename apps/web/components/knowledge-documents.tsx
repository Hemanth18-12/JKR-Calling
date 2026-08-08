"use client";

import { DocumentCreate, SOURCE_TYPE_OPTIONS, APPROVAL_STATE_VARIANT, type DocumentOut } from "@jkr/contracts";
import { ApiClientError, knowledgeApi } from "@jkr/sdk";
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
  Textarea,
  useToast,
} from "@jkr/ui";
import { zodResolver } from "@hookform/resolvers/zod";
import { FileText, Search } from "lucide-react";
import { useRouter } from "next/navigation";
import * as React from "react";
import { useForm } from "react-hook-form";

function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = reader.result as string;
      resolve(result.split(",")[1] ?? "");
    };
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

function NewDocumentForm({ workspaceId }: { workspaceId: string }) {
  const router = useRouter();
  const { toast } = useToast();
  const [formError, setFormError] = React.useState<string | null>(null);
  const [file, setFile] = React.useState<File | null>(null);
  const {
    register,
    handleSubmit,
    watch,
    formState: { errors, isSubmitting },
  } = useForm<DocumentCreate>({ resolver: zodResolver(DocumentCreate), defaultValues: { source_type: "manual_faq" } });
  const sourceType = watch("source_type");
  const needsFile = sourceType === "pdf" || sourceType === "docx" || sourceType === "csv";

  const onSubmit = async (data: DocumentCreate) => {
    setFormError(null);
    try {
      let payload = data;
      if (needsFile) {
        if (!file) {
          setFormError("Choose a file to upload.");
          return;
        }
        payload = { ...data, file_base64: await fileToBase64(file) };
      }
      const doc = await knowledgeApi.createDocument(workspaceId, payload);
      // Immediately process (chunk + embed) so it's ready for review.
      await knowledgeApi.processDocument(workspaceId, doc.id);
      toast({ title: "Document added", description: "Now needs review before it can be used in calls.", variant: "success" });
      router.refresh();
    } catch (err) {
      setFormError(err instanceof ApiClientError ? err.message : "Could not add document.");
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Add knowledge</CardTitle>
        <CardDescription>New content starts as draft, then needs review before agents can use it.</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div>
            <Label htmlFor="kb-source-type">Source type</Label>
            <select id="kb-source-type" className="flex h-10 w-full rounded-md border border-border bg-surface px-3 py-2 text-sm" {...register("source_type")}>
              {SOURCE_TYPE_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </div>
          <div>
            <Label htmlFor="kb-title">Title</Label>
            <Input id="kb-title" placeholder="Root canal FAQ" {...register("title")} />
            <FieldError>{errors.title?.message}</FieldError>
          </div>
          {sourceType === "manual_faq" || sourceType === "text" ? (
            <div>
              <Label htmlFor="kb-raw-text">Content</Label>
              <Textarea id="kb-raw-text" rows={5} placeholder="One fact per line works well for FAQs." {...register("raw_text")} />
            </div>
          ) : null}
          {sourceType === "website" ? (
            <div>
              <Label htmlFor="kb-url">Website URL</Label>
              <Input id="kb-url" placeholder="https://example.com/faq" {...register("source_url")} />
            </div>
          ) : null}
          {needsFile ? (
            <div>
              <Label htmlFor="kb-file">File</Label>
              <input
                id="kb-file"
                type="file"
                accept={sourceType === "pdf" ? ".pdf" : sourceType === "docx" ? ".docx" : ".csv"}
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                className="block w-full text-sm text-muted-foreground"
              />
            </div>
          ) : null}
          {formError ? <p className="text-sm text-danger">{formError}</p> : null}
          <Button type="submit" className="w-full" loading={isSubmitting}>
            Add &amp; process
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

function DocumentRow({ workspaceId, document }: { workspaceId: string; document: DocumentOut }) {
  const router = useRouter();
  const { toast } = useToast();
  const [busy, setBusy] = React.useState(false);

  const act = async (action: "approve" | "reject") => {
    setBusy(true);
    try {
      if (action === "approve") await knowledgeApi.approveDocument(workspaceId, document.id, null);
      else await knowledgeApi.rejectDocument(workspaceId, document.id, null);
      router.refresh();
    } catch (err) {
      toast({ title: "Action failed", description: err instanceof ApiClientError ? err.message : undefined, variant: "danger" });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex items-center justify-between border-b border-border py-3 last:border-0">
      <div className="flex items-center gap-3">
        <FileText className="h-4 w-4 text-muted-foreground" />
        <div>
          <p className="text-sm font-medium">{document.title}</p>
          <p className="text-xs text-muted-foreground">
            {document.source_type} · {document.chunk_count} chunk{document.chunk_count === 1 ? "" : "s"}
          </p>
        </div>
      </div>
      <div className="flex items-center gap-2">
        <Badge variant={APPROVAL_STATE_VARIANT[document.approval_state] ?? "secondary"}>{document.approval_state}</Badge>
        {document.approval_state === "needs_review" ? (
          <>
            <Button size="sm" variant="secondary" onClick={() => act("approve")} loading={busy}>
              Approve
            </Button>
            <Button size="sm" variant="ghost" onClick={() => act("reject")} loading={busy}>
              Reject
            </Button>
          </>
        ) : null}
      </div>
    </div>
  );
}

function SearchTester({ workspaceId }: { workspaceId: string }) {
  const [query, setQuery] = React.useState("");
  const [results, setResults] = React.useState<{ text: string; score: number; document_title: string }[] | null>(null);
  const [aboveThreshold, setAboveThreshold] = React.useState(true);
  const [loading, setLoading] = React.useState(false);

  const run = async () => {
    if (!query.trim()) return;
    setLoading(true);
    try {
      const result = await knowledgeApi.search(workspaceId, { query, top_k: 3 });
      setResults(result.results);
      setAboveThreshold(result.above_threshold);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Test retrieval</CardTitle>
        <CardDescription>What an agent would find for a given customer question — approved chunks only.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex gap-2">
          <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="How much does root canal cost?" onKeyDown={(e) => e.key === "Enter" && run()} />
          <Button onClick={run} loading={loading}>
            <Search className="h-4 w-4" />
          </Button>
        </div>
        {results !== null ? (
          results.length === 0 ? (
            <p className="text-sm text-muted-foreground">No approved knowledge yet.</p>
          ) : !aboveThreshold ? (
            <p className="text-sm text-warning">Best match is below the confidence threshold — the agent would ask a clarifying question or offer a human callback instead of answering.</p>
          ) : (
            <ul className="space-y-2">
              {results.map((r, i) => (
                <li key={i} className="rounded-md border border-border p-2 text-sm">
                  <p className="text-xs text-muted-foreground">{r.document_title} · score {r.score.toFixed(2)}</p>
                  <p>{r.text}</p>
                </li>
              ))}
            </ul>
          )
        ) : null}
      </CardContent>
    </Card>
  );
}

export function KnowledgeDocuments({ workspaceId, documents }: { workspaceId: string; documents: DocumentOut[] }) {
  return (
    <div className="grid gap-6 lg:grid-cols-3">
      <Card className="lg:col-span-2">
        <CardHeader>
          <CardTitle>Documents</CardTitle>
          <CardDescription>{documents.length} document{documents.length === 1 ? "" : "s"} in this workspace.</CardDescription>
        </CardHeader>
        <CardContent>
          {documents.length === 0 ? (
            <p className="text-sm text-muted-foreground">No knowledge yet — add your first document.</p>
          ) : (
            documents.map((d) => <DocumentRow key={d.id} workspaceId={workspaceId} document={d} />)
          )}
        </CardContent>
      </Card>
      <div className="space-y-6">
        <NewDocumentForm workspaceId={workspaceId} />
        <SearchTester workspaceId={workspaceId} />
      </div>
    </div>
  );
}
