"use client";

import Image from "next/image";
import { useRouter } from "next/navigation";
import { useState, type ChangeEvent, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { browserApi } from "@/lib/api/browser";
import { errorMessage } from "@/lib/api/errors";
import { uploadPhoto, type Photo } from "@/lib/api/upload";
import { FormMessage } from "./field";

const ACCEPT = "image/jpeg,image/png,image/webp";

function PhotoTile({
  tenantId,
  photo,
  position,
  count,
  onMove,
  onError,
}: {
  tenantId: string;
  photo: Photo;
  position: number;
  count: number;
  onMove: (from: number, to: number) => void;
  onError: (message: string | null) => void;
}) {
  const router = useRouter();
  const [caption, setCaption] = useState(photo.caption);
  const label = `photo ${position + 1}`;

  async function saveCaption(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const { error } = await browserApi.PATCH("/v1/tenants/{tenant_id}/photos/{photo_id}", {
      params: { path: { tenant_id: tenantId, photo_id: photo.id } },
      body: { caption },
    });
    onError(error ? errorMessage(error) : null);
    if (!error) router.refresh();
  }

  async function remove() {
    if (!window.confirm(`Delete ${label}?`)) return;
    const { error } = await browserApi.DELETE("/v1/tenants/{tenant_id}/photos/{photo_id}", {
      params: { path: { tenant_id: tenantId, photo_id: photo.id } },
    });
    onError(error ? errorMessage(error) : null);
    if (!error) router.refresh();
  }

  return (
    <li className="grid gap-2 rounded-lg border border-border p-2">
      {/* Served through the API after a membership check; Next's optimizer can't send the
          session cookie, so the image is used as stored. */}
      <Image
        src={photo.url}
        alt={photo.caption || `Lot ${label}`}
        width={photo.width ?? 400}
        height={photo.height ?? 300}
        unoptimized
        className="aspect-[4/3] w-full rounded-md bg-muted object-cover"
      />
      <form onSubmit={saveCaption} className="flex gap-2">
        <Input
          aria-label={`Caption for ${label}`}
          placeholder="Caption"
          value={caption}
          maxLength={300}
          onChange={(event) => setCaption(event.target.value)}
        />
        <Button type="submit" variant="outline" size="sm" disabled={caption === photo.caption}>
          Save
        </Button>
      </form>
      <div className="flex flex-wrap gap-1">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          aria-label={`Move ${label} earlier`}
          disabled={position === 0}
          onClick={() => onMove(position, position - 1)}
        >
          ← Earlier
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          aria-label={`Move ${label} later`}
          disabled={position === count - 1}
          onClick={() => onMove(position, position + 1)}
        >
          Later →
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="ml-auto"
          aria-label={`Delete ${label}`}
          onClick={remove}
        >
          Delete
        </Button>
      </div>
    </li>
  );
}

/** A lot's photos: upload several at once, caption, reorder and delete. The first photo is the
 * one shown first on the public lot page. */
export function PhotosCard({
  tenantId,
  lotId,
  photos,
}: {
  tenantId: string;
  lotId: string;
  photos: Photo[];
}) {
  const router = useRouter();
  const [progress, setProgress] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function upload(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files ?? []);
    event.target.value = "";
    if (files.length === 0) return;
    const failures: string[] = [];
    for (const [index, file] of files.entries()) {
      setProgress(`Uploading ${index + 1} of ${files.length}…`);
      const result = await uploadPhoto(tenantId, lotId, file);
      if (!result.ok) failures.push(`${file.name}: ${result.error}`);
    }
    setProgress(null);
    setError(failures.length > 0 ? failures.join(" ") : null);
    router.refresh();
  }

  async function move(from: number, to: number) {
    const ids = photos.map((photo) => photo.id);
    const [moved] = ids.splice(from, 1);
    if (moved === undefined) return;
    ids.splice(to, 0, moved);
    const { error: failure } = await browserApi.PUT(
      "/v1/tenants/{tenant_id}/lots/{lot_id}/photos/order",
      { params: { path: { tenant_id: tenantId, lot_id: lotId } }, body: { photo_ids: ids } },
    );
    setError(failure ? errorMessage(failure) : null);
    router.refresh();
  }

  return (
    <div className="grid gap-4">
      {photos.length === 0 ? (
        <p className="text-sm text-muted-foreground">No photos yet.</p>
      ) : (
        <ol className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {photos.map((photo, position) => (
            <PhotoTile
              key={`${photo.id}-${photo.caption}`}
              tenantId={tenantId}
              photo={photo}
              position={position}
              count={photos.length}
              onMove={move}
              onError={setError}
            />
          ))}
        </ol>
      )}
      <div className="grid gap-1.5">
        <Label htmlFor="photo-upload">Add photos</Label>
        <Input
          id="photo-upload"
          type="file"
          accept={ACCEPT}
          multiple
          onChange={upload}
          disabled={progress !== null}
        />
        <p className="text-xs text-muted-foreground">
          JPEG, PNG or WebP, up to 15 MB each. Location data in photos is removed on upload.
        </p>
      </div>
      <FormMessage error={error} success={progress} />
    </div>
  );
}
