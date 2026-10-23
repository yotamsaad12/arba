import createFetchClient from "openapi-fetch";
import createQueryClient from "openapi-react-query";
import type { components, paths } from "./schema";

export type { paths };
export type Schemas = components["schemas"];
export type Project = Schemas["ProjectOut"];
export type ProjectDetail = Schemas["ProjectDetail"];
export type Requirement = Schemas["RequirementOut"];
export type Stage = Schemas["Stage"];
export type NextSteps = Schemas["NextSteps"];
export type Template = Schemas["TemplateOut"];
export type Me = Schemas["MeOut"];
export type TokenOut = Schemas["TokenOut"];
export type BuildState = Schemas["BuildState"];
export type ThreadSummary = Schemas["ThreadSummary"];
export type ThreadDetail = Schemas["ThreadDetail"];
export type MessageOut = Schemas["MessageOut"];
export type DocumentOut = Schemas["DocumentOut"];
export type Suggestion = Schemas["SuggestionOut"];
export type AcceptResult = Schemas["AcceptResult"];
export type NotificationItem = Schemas["NotificationOut"];
export type UserSettings = Schemas["SettingsOut"];
export type SimMessage = Schemas["SimMessage"];
export type Locality = Schemas["LocalityOut"];
export type PermitInfo = Schemas["PermitOut"];
export type PermitFields = Schemas["PermitFields"];
export type AuthorityInfo = Schemas["AuthorityOut"];
export type ScanInfo = Schemas["ScanOut"];
export type CatchUpReport = Schemas["CatchUpReport"];
export type ReportItem = Schemas["ReportItem"];
export type PermitCondition = Schemas["ConditionOut"];
export type Draft = Schemas["DraftOut"];
export type Contact = Schemas["TeamMemberOut"];
export type DocumentRequestInfo = Schemas["RequestOut"];
export type PublicRequest = Schemas["PublicRequestOut"];

export interface ApiOptions {
  /** Empty for the web app, which reaches the API through the dev proxy / same origin. */
  baseUrl?: string;
  /** "web" keeps the refresh token in an httpOnly cookie; "mobile" stores it itself. */
  client?: "web" | "mobile";
  loadRefreshToken?: () => Promise<string | null>;
  saveRefreshToken?: (token: string | null) => Promise<void>;
  onSessionExpired?: () => void;
}

const AUTH_PATHS = ["/api/v1/auth/login", "/api/v1/auth/register", "/api/v1/auth/refresh"];

export function createApi(options: ApiOptions = {}) {
  const { baseUrl = "", client = "web" } = options;
  let accessToken: string | null = null;
  let refreshing: Promise<boolean> | null = null;

  async function setSession(tokens: TokenOut): Promise<void> {
    accessToken = tokens.access_token;
    if (tokens.refresh_token) await options.saveRefreshToken?.(tokens.refresh_token);
  }

  async function clearSession(): Promise<void> {
    accessToken = null;
    await options.saveRefreshToken?.(null);
  }

  /** Gets a new access token. Concurrent callers share one request. */
  function refresh(): Promise<boolean> {
    refreshing ??= (async () => {
      const refreshToken = client === "mobile" ? await options.loadRefreshToken?.() : null;
      if (client === "mobile" && !refreshToken) return false;
      const response = await fetch(`${baseUrl}/api/v1/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ client, refresh_token: refreshToken }),
      });
      if (!response.ok) {
        await clearSession();
        return false;
      }
      await setSession((await response.json()) as TokenOut);
      return true;
    })().finally(() => {
      refreshing = null;
    });
    return refreshing;
  }

  async function authFetch(request: Request): Promise<Response> {
    const retry = request.clone();
    if (accessToken) request.headers.set("Authorization", `Bearer ${accessToken}`);
    const response = await fetch(request);
    if (response.status !== 401 || AUTH_PATHS.some((p) => request.url.includes(p))) {
      return response;
    }
    if (!(await refresh())) {
      options.onSessionExpired?.();
      return response;
    }
    retry.headers.set("Authorization", `Bearer ${accessToken}`);
    return fetch(retry);
  }

  const fetchClient = createFetchClient<paths>({ baseUrl, fetch: authFetch });
  const $api = createQueryClient(fetchClient);

  return { fetchClient, $api, setSession, clearSession, refresh, client };
}

export type Api = ReturnType<typeof createApi>;

/** Stable error code from either an AppError body or a FastAPI validation error. */
export function errorCode(error: unknown): string {
  if (error && typeof error === "object") {
    if ("error" in error) {
      const inner = (error as { error?: { code?: unknown } }).error;
      if (inner && typeof inner.code === "string") return inner.code;
    }
    if ("detail" in error) return "validation_error";
  }
  return "unknown_error";
}

export function errorDetails(error: unknown): Record<string, unknown> {
  if (error && typeof error === "object" && "error" in error) {
    return (error as { error?: { details?: Record<string, unknown> } }).error?.details ?? {};
  }
  return {};
}
