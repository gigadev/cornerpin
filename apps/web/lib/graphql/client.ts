import "server-only";
import type { TypedDocumentNode } from "@graphql-typed-document-node/core";
import { print } from "graphql";
import { apiAuthHeaders } from "@/lib/api/identity";
import { apiBaseUrl } from "@/lib/api/proxy";

type GraphqlResponse<T> = { data?: T | null; errors?: { message: string }[] };

/** Run a public GraphQL query from the server (ADR-007). Published listings only: the API
 * answers these as cornerpin_public. */
export async function publicQuery<Result, Variables>(
  document: TypedDocumentNode<Result, Variables>,
  variables: Variables,
): Promise<Result> {
  const response = await fetch(`${apiBaseUrl()}/graphql`, {
    method: "POST",
    headers: { "content-type": "application/json", ...(await apiAuthHeaders()) },
    body: JSON.stringify({ query: print(document), variables }),
    // Publishing should show at once (ADR-027).
    cache: "no-store",
  });
  const body = (await response.json()) as GraphqlResponse<Result>;
  if (!response.ok || body.errors?.length || !body.data) {
    const reason = body.errors?.map((error) => error.message).join("; ") ?? response.statusText;
    throw new Error(`GraphQL query failed: ${reason}`);
  }
  return body.data;
}
