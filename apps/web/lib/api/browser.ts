import createClient from "openapi-fetch";
import type { paths } from "./schema";

/** API client for client components. Same origin: requests go through the /v1 proxy. */
export const browserApi = createClient<paths>({ baseUrl: "" });
