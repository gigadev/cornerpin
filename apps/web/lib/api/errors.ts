// FastAPI errors are either {"detail": "message"} or, for validation, {"detail": [{msg, loc}]}.

type ValidationIssue = { msg?: unknown; loc?: unknown };

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function fieldName(loc: unknown): string | null {
  if (!Array.isArray(loc)) return null;
  const last: unknown = loc[loc.length - 1];
  return typeof last === "string" && last !== "body" ? last.replaceAll("_", " ") : null;
}

/** A sentence to show the person, from whatever the API returned. */
export function errorMessage(error: unknown, fallback = "Something went wrong. Try again."): string {
  if (!isRecord(error)) return fallback;
  const { detail } = error;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const messages = detail
      .filter((issue): issue is ValidationIssue => isRecord(issue))
      .map((issue) => {
        const message = typeof issue.msg === "string" ? issue.msg.replace(/^Value error, /, "") : "";
        const field = fieldName(issue.loc);
        return field && message ? `${field}: ${message}` : message;
      })
      .filter(Boolean);
    if (messages.length > 0) return messages.join(". ");
  }
  return fallback;
}
