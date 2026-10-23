// Mirrors backend/app/core/enums.py. Keep the two in sync.

export const REQUIREMENT_STATUSES = [
  "not_started",
  "blocked",
  "ready",
  "in_progress",
  "waiting_for_authority",
  "needs_fix",
  "done",
  "not_applicable",
] as const;
export type RequirementStatus = (typeof REQUIREMENT_STATUSES)[number];

export const DONE_STATUSES: ReadonlySet<RequirementStatus> = new Set(["done", "not_applicable"]);

export type Tone = "neutral" | "info" | "warning" | "success" | "danger" | "muted";

export const STATUS_TONE: Record<RequirementStatus, Tone> = {
  not_started: "neutral",
  blocked: "muted",
  ready: "info",
  in_progress: "warning",
  waiting_for_authority: "warning",
  needs_fix: "danger",
  done: "success",
  not_applicable: "muted",
};

/** Statuses a person can set. "blocked" and "ready" are derived by the dependency engine. */
export type ManualStatus = Exclude<RequirementStatus, "blocked" | "ready">;

/** The status changes a person can make from each status, in button order. */
export function statusActions(status: RequirementStatus, optional: boolean): ManualStatus[] {
  // Any item can be "not needed" (authorities' own lists say "אין צורך"); optional ones lead with it.
  switch (status) {
    case "not_started":
    case "ready":
    case "blocked":
      return optional ? ["not_applicable", "in_progress", "done"] : ["in_progress", "done", "not_applicable"];
    case "in_progress":
      return ["waiting_for_authority", "done", "needs_fix"];
    case "waiting_for_authority":
      return ["done", "needs_fix"];
    case "needs_fix":
      return ["in_progress", "done"];
    case "done":
      return ["needs_fix"];
    case "not_applicable":
      return ["not_started"];
  }
}

export const CLIENT_TYPES = ["private", "business"] as const;
export type ClientType = (typeof CLIENT_TYPES)[number];
