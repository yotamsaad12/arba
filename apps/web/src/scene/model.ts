import type { BuildState } from "@arba/api-client";

/** Template stages the construction scene knows how to draw, in build order. */
export const STAGES = [
  "pre",
  "foundations",
  "skeleton",
  "mamad",
  "envelope",
  "systems",
  "finish",
  "green",
  "form4",
] as const;
export type StageKey = (typeof STAGES)[number];

export const STAGE_ICON: Record<StageKey, string> = {
  pre: "📋",
  foundations: "⛏️",
  skeleton: "🏗️",
  mamad: "🛡️",
  envelope: "🧱",
  systems: "🔌",
  finish: "🎨",
  green: "🌱",
  form4: "🏆",
};

export interface SceneModel {
  /** Overall completion, 0..1. */
  overall: number;
  /** Completion per stage, 0..1. */
  stage: Record<StageKey, number>;
  /** Skeleton completion per floor; index 0 is the ground floor. */
  floors: number[];
  /** Green building work was actually done (not just marked not applicable). */
  greenInstalled: boolean;
  focus: StageKey | null;
  focusFloor: number | null;
  complete: boolean;
}

export function isStageKey(value: unknown): value is StageKey {
  return typeof value === "string" && (STAGES as readonly string[]).includes(value);
}

export function sceneModel(build: BuildState, floorCount: number): SceneModel {
  const totals = new Map<string, { done: number; total: number; skipped: number }>();
  const floors = Array.from({ length: Math.max(1, floorCount) }, () => 0);
  for (const s of build.stages) {
    const t = totals.get(s.stage) ?? { done: 0, total: 0, skipped: 0 };
    t.done += s.done;
    t.total += s.total;
    t.skipped += s.skipped;
    totals.set(s.stage, t);
    if (s.stage === "skeleton" && s.floor && s.floor <= floors.length) {
      floors[s.floor - 1] = s.total ? s.done / s.total : 0;
    }
  }
  const stage = Object.fromEntries(
    STAGES.map((k) => {
      const t = totals.get(k);
      return [k, t && t.total ? t.done / t.total : 0];
    }),
  ) as Record<StageKey, number>;
  const green = totals.get("green");
  const { done, total } = build.progress;

  return {
    overall: total ? done / total : 0,
    stage,
    floors,
    greenInstalled: !!green && green.done - green.skipped > 0,
    focus: isStageKey(build.focus_stage) ? build.focus_stage : null,
    focusFloor: build.focus_floor ?? null,
    complete: total > 0 && done === total,
  };
}

// Share of the demo timeline each stage takes. The skeleton is split across floors.
const DEMO_WEIGHTS: Record<StageKey, number> = {
  pre: 0.08,
  foundations: 0.1,
  skeleton: 0.26,
  mamad: 0.06,
  envelope: 0.12,
  systems: 0.1,
  finish: 0.14,
  green: 0.06,
  form4: 0.08,
};

/** A synthetic project at point t (0..1) of its life, for the sign-in screen. */
export function demoModel(t: number, floorCount = 2): SceneModel {
  const clamp = (v: number) => Math.min(1, Math.max(0, v));
  const stage = {} as Record<StageKey, number>;
  let start = 0;
  let focus: StageKey | null = null;
  let focusFloor: number | null = null;
  const floors = Array.from({ length: floorCount }, () => 0);

  for (const key of STAGES) {
    const length = DEMO_WEIGHTS[key];
    stage[key] = clamp((t - start) / length);
    if (!focus && t < start + length) focus = key;
    if (key === "skeleton") {
      for (let f = 0; f < floorCount; f++) {
        floors[f] = clamp((t - start - (f * length) / floorCount) / (length / floorCount));
        if (focus === "skeleton" && focusFloor === null && floors[f]! < 1) focusFloor = f + 1;
      }
    }
    start += length;
  }

  return {
    overall: clamp(t),
    stage,
    floors,
    greenInstalled: true,
    focus,
    focusFloor,
    complete: t >= 1,
  };
}
