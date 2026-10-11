import createFetchClient, { type Middleware } from "openapi-fetch";
import createClient from "openapi-react-query";
import type { components, paths } from "./schema";

/** Every response model the API publishes, by name — generated from
 * backend's OpenAPI schema (`npm run api`), never written by hand. */
export type Api = components["schemas"];

// An expired session anywhere sends you to the login page and back.
const authRedirect: Middleware = {
  onResponse({ response }) {
    if (response.status === 401 && !window.location.pathname.startsWith("/login")) {
      const next = encodeURIComponent(window.location.pathname + window.location.search);
      window.location.assign(`/login?next=${next}`);
    }
  },
};

export const fetchClient = createFetchClient<paths>({ baseUrl: "", credentials: "same-origin" });
fetchClient.use(authRedirect);

/** Typed TanStack Query hooks: `$api.useQuery("get", "/api/ucl/overview")`. */
export const $api = createClient(fetchClient);
