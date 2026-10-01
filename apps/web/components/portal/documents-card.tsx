"use client";

import { useRouter } from "next/navigation";
import { useRef, useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { browserApi } from "@/lib/api/browser";
import { errorMessage } from "@/lib/api/errors";
import { uploadDocument, type LotDocument } from "@/lib/api/upload";
import { DOCUMENT_KINDS, documentLabel, formatBytes, type DocumentKind } from "@/lib/format";
import { Field, FormMessage } from "./field";

function isKind(value: string): value is DocumentKind {
  return (DOCUMENT_KINDS as readonly string[]).includes(value);
}

/** A lot's documents: plat, survey, covenants, utilities and anything else worth sharing. */
export function DocumentsCard({
  tenantId,
  lotId,
  documents,
}: {
  tenantId: string;
  lotId: string;
  documents: LotDocument[];
}) {
  const router = useRouter();
  const fileInput = useRef<HTMLInputElement>(null);
  const [kind, setKind] = useState<DocumentKind>("plat");
  const [title, setTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const file = fileInput.current?.files?.[0];
    if (!file) {
      setError("Choose a file to upload.");
      return;
    }
    setBusy(true);
    const result = await uploadDocument(tenantId, lotId, file, kind, title || documentLabel(kind));
    setBusy(false);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    setError(null);
    setTitle("");
    if (fileInput.current) fileInput.current.value = "";
    router.refresh();
  }

  async function remove(document: LotDocument) {
    if (!window.confirm(`Delete ${document.title}?`)) return;
    const { error: failure } = await browserApi.DELETE(
      "/v1/tenants/{tenant_id}/documents/{document_id}",
      { params: { path: { tenant_id: tenantId, document_id: document.id } } },
    );
    setError(failure ? errorMessage(failure) : null);
    router.refresh();
  }

  return (
    <div className="grid gap-4">
      {documents.length === 0 ? (
        <p className="text-sm text-muted-foreground">No documents yet.</p>
      ) : (
        <ul className="divide-y divide-border">
          {documents.map((document) => (
            <li key={document.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2">
              <span className="w-20 text-sm text-muted-foreground">
                {documentLabel(document.kind)}
              </span>
              <span className="font-medium">{document.title}</span>
              <span className="text-sm text-muted-foreground">
                {formatBytes(document.size_bytes)}
              </span>
              <span className="ml-auto flex gap-1">
                <Button asChild variant="outline" size="sm">
                  <a href={document.url} download aria-label={`Download ${document.title}`}>
                    Download
                  </a>
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  aria-label={`Delete ${document.title}`}
                  onClick={() => remove(document)}
                >
                  Delete
                </Button>
              </span>
            </li>
          ))}
        </ul>
      )}
      <form onSubmit={upload} className="grid gap-4 sm:grid-cols-[10rem_1fr] sm:items-end">
        <Field id="document-kind" label="Kind">
          <Select
            value={kind}
            onValueChange={(value) => {
              if (isKind(value)) setKind(value);
            }}
          >
            <SelectTrigger id="document-kind" className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {DOCUMENT_KINDS.map((option) => (
                <SelectItem key={option} value={option}>
                  {documentLabel(option)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>
        <Field id="document-title" label="Title" hint="Also the file name people download.">
          <Input
            id="document-title"
            placeholder={documentLabel(kind)}
            maxLength={200}
            value={title}
            onChange={(event) => setTitle(event.target.value)}
          />
        </Field>
        <Field id="document-file" label="File" hint="PDF, JPEG or PNG, up to 25 MB.">
          <Input
            id="document-file"
            ref={fileInput}
            type="file"
            accept="application/pdf,image/jpeg,image/png"
          />
        </Field>
        <div>
          <Button type="submit" variant="outline" disabled={busy}>
            {busy ? "Uploading…" : "Upload document"}
          </Button>
        </div>
      </form>
      <FormMessage error={error} />
    </div>
  );
}
