import { errorMessage } from "./errors";
import type { components } from "./schema";

// File uploads use multipart forms, which the generated client cannot type well, so these two
// helpers post the form themselves and return the API's own response types.

export type Photo = components["schemas"]["PhotoOut"];
export type LotDocument = components["schemas"]["DocumentOut"];
export type DocumentKind = components["schemas"]["DocumentKind"];
export type Overlay = components["schemas"]["OverlayOut"];

export type UploadResult<T> = { ok: true; value: T } | { ok: false; error: string };

async function postForm<T>(path: string, form: FormData): Promise<UploadResult<T>> {
  let response: Response;
  try {
    response = await fetch(path, { method: "POST", body: form });
  } catch {
    return { ok: false, error: "The upload didn't reach the server. Check the connection." };
  }
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    return { ok: false, error: errorMessage(body, `Upload failed (${response.status}).`) };
  }
  return { ok: true, value: body as T };
}

export function uploadPhoto(
  tenantId: string,
  lotId: string,
  file: File,
): Promise<UploadResult<Photo>> {
  const form = new FormData();
  form.append("file", file);
  return postForm(`/v1/tenants/${tenantId}/lots/${lotId}/photos`, form);
}

export function uploadDocument(
  tenantId: string,
  lotId: string,
  file: File,
  kind: DocumentKind,
  title: string,
): Promise<UploadResult<LotDocument>> {
  const form = new FormData();
  form.append("file", file);
  form.append("kind", kind);
  form.append("title", title);
  return postForm(`/v1/tenants/${tenantId}/lots/${lotId}/documents`, form);
}

export function uploadOverlay(
  tenantId: string,
  subdivisionId: string,
  file: File,
): Promise<UploadResult<Overlay>> {
  const form = new FormData();
  form.append("file", file);
  return postForm(`/v1/tenants/${tenantId}/subdivisions/${subdivisionId}/overlay`, form);
}
