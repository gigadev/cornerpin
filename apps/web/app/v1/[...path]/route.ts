import type { NextRequest } from "next/server";
import { apiBaseUrl, forwardRequestHeaders, forwardResponseHeaders } from "@/lib/api/proxy";

export const dynamic = "force-dynamic";

async function proxy(request: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params;
  const target = new URL(`/v1/${path.map(encodeURIComponent).join("/")}`, apiBaseUrl());
  target.search = request.nextUrl.search;

  const hasBody = !["GET", "HEAD"].includes(request.method);
  const upstream = await fetch(target, {
    method: request.method,
    headers: forwardRequestHeaders(request.headers, null),
    body: hasBody ? await request.arrayBuffer() : undefined,
    redirect: "manual",
    cache: "no-store",
  });

  const body = upstream.status === 204 || upstream.status === 304 ? null : upstream.body;
  return new Response(body, {
    status: upstream.status,
    headers: forwardResponseHeaders(upstream.headers),
  });
}

export { proxy as DELETE, proxy as GET, proxy as PATCH, proxy as POST, proxy as PUT };
