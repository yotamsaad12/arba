import type { NextSteps, ProjectDetail, Requirement } from "@arba/api-client";
import { DONE_STATUSES, type RequirementStatus } from "@arba/shared";
import { AnimatePresence, LayoutGroup, animate, motion, useMotionValue, useTransform } from "motion/react";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Link, useParams, useSearchParams } from "react-router";
import { useCelebrate } from "../components/Celebrations";
import { Alert, Spinner, cx } from "../components/ui";
import { $api } from "../lib/api";
import { useErrorMessage } from "../lib/useErrorMessage";
import { CatchUpEntry } from "./Import";
import { DocumentsView } from "../project/DocumentsView";
import { InboxView } from "../project/InboxView";
import { AuthoritiesPanel, PermitBanner } from "../project/PermitPanel";
import { ConditionsCard } from "../project/ConditionsCard";
import { DraftsPanel } from "../project/DraftsPanel";
import { RequirementCard } from "../project/RequirementCard";
import { ApprovalsPanel } from "../project/SuggestionCard";
import { STAGE_ICON, isStageKey, sceneModel } from "../scene/model";
import { useFocusLabel } from "../scene/useFocusLabel";
import { LiveWorld } from "../world/LiveWorld";
import { useAuthorities } from "../world/authorities";

const TABS = ["now", "all", "inbox", "documents"] as const;
type Tab = (typeof TABS)[number];
const TAB_LABEL = {
  now: "project.tabNow",
  all: "project.tabAll",
  inbox: "project.tabInbox",
  documents: "project.tabDocuments",
} as const;
const TAB_SHORT_LABEL = { ...TAB_LABEL, now: "project.tabNowShort", all: "project.tabAllShort" } as const;

export function ProjectPage() {
  const { projectId = "" } = useParams();
  const { t } = useTranslation();
  const message = useErrorMessage();
  const [search, setSearch] = useSearchParams();
  const tab: Tab = TABS.find((key) => key === search.get("tab")) ?? "now";
  const path = { params: { path: { project_id: projectId } } };

  const project = $api.useQuery("get", "/api/v1/projects/{project_id}", path);
  const requirements = $api.useQuery("get", "/api/v1/projects/{project_id}/requirements", path);
  const steps = $api.useQuery("get", "/api/v1/projects/{project_id}/next-steps", path);
  // New mail and uploads are classified in the background; keep the approvals fresh.
  const suggestions = $api.useQuery("get", "/api/v1/projects/{project_id}/suggestions", path, {
    refetchInterval: 15_000,
  });
  const titles = useMemo(
    () => new Map(requirements.data?.requirements.map((r) => [r.id, r.title])),
    [requirements.data],
  );

  if (project.error) return <Alert>{message(project.error)}</Alert>;
  if (!project.data) return <Spinner label={t("app.loading")} />;

  const p = project.data;
  const canEdit = p.role !== "viewer";
  const goToStage = (stage: string) => {
    setSearch({ tab: "all" }, { replace: true });
    window.setTimeout(
      () => document.getElementById(`stage-${stage}`)?.scrollIntoView({ behavior: "smooth", block: "start" }),
      120,
    );
  };

  return (
    <div className="space-y-6">
      <Link to="/" className="inline-flex items-center gap-1 text-sm font-medium text-ink-soft hover:text-ink">
        → {t("projects.title")}
      </Link>

      <Hero project={p} steps={steps.data} />
      <StageStepper project={p} onSelect={goToStage} />

      <LayoutGroup id="tabs">
        <nav className="relative grid grid-cols-4 rounded-full border-2 border-ink bg-surface p-1" role="tablist">
          {TABS.map((key) => {
            const badge =
              key === "inbox" ? p.inbox.unread : key === "now" ? (suggestions.data?.length ?? 0) : 0;
            return (
              <button
                key={key}
                role="tab"
                aria-selected={tab === key}
                className={cx(
                  "relative min-h-11 rounded-full px-1 font-display text-sm font-bold transition-colors sm:text-base",
                  tab === key ? "text-white" : "text-ink-soft hover:text-ink",
                )}
                onClick={() => setSearch(key === "now" ? {} : { tab: key }, { replace: true })}
              >
                {tab === key && (
                  <motion.span
                    layoutId="tab-pill"
                    className="absolute inset-0 rounded-full bg-ink"
                    transition={{ type: "spring", stiffness: 420, damping: 34 }}
                  />
                )}
                <span className="relative hidden sm:inline">{t(TAB_LABEL[key])}</span>
                <span className="relative sm:hidden">{t(TAB_SHORT_LABEL[key])}</span>
                <AnimatePresence>
                  {badge > 0 && (
                    <motion.span
                      key={badge}
                      initial={{ scale: 0 }}
                      animate={{ scale: 1 }}
                      exit={{ scale: 0 }}
                      className="absolute -top-2 end-1 grid min-w-5 place-items-center rounded-full border-2 border-ink bg-accent px-1 text-xs text-ink"
                    >
                      {badge}
                    </motion.span>
                  )}
                </AnimatePresence>
              </button>
            );
          })}
        </nav>
      </LayoutGroup>

      <AnimatePresence mode="wait">
        <motion.div
          key={tab}
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.3 }}
        >
          {tab === "now" && (
            <div className="space-y-8">
              <PermitBanner projectId={projectId} permit={p.permit} canEdit={canEdit} />
              <ConditionsCard projectId={projectId} canEdit={canEdit} />
              {canEdit && <CatchUpEntry projectId={projectId} />}
              {requirements.data && (
                <ApprovalsPanel
                  projectId={projectId}
                  suggestions={suggestions.data ?? []}
                  stages={requirements.data.stages}
                  requirements={requirements.data.requirements}
                  canEdit={canEdit}
                />
              )}
              <DraftsPanel projectId={projectId} canEdit={canEdit} />
              {steps.data ? (
                <NextStepsView projectId={projectId} steps={steps.data} titles={titles} canEdit={canEdit} />
              ) : (
                <Spinner label={t("app.loading")} />
              )}
              <AuthoritiesPanel projectId={projectId} />
            </div>
          )}
          {tab !== "now" && !requirements.data && <Spinner label={t("app.loading")} />}
          {tab === "all" && requirements.data && (
            <AllRequirementsView
              projectId={projectId}
              stages={requirements.data.stages}
              requirements={requirements.data.requirements}
              titles={titles}
              canEdit={canEdit}
            />
          )}
          {tab === "inbox" && requirements.data && (
            <InboxView
              projectId={projectId}
              suggestions={suggestions.data ?? []}
              inboxAddress={p.inbox_address}
              canEdit={canEdit}
              stages={requirements.data.stages}
              requirements={requirements.data.requirements}
            />
          )}
          {tab === "documents" && requirements.data && (
            <DocumentsView
              projectId={projectId}
              suggestions={suggestions.data ?? []}
              projectName={p.name}
              canEdit={canEdit}
              stages={requirements.data.stages}
              requirements={requirements.data.requirements}
            />
          )}
        </motion.div>
      </AnimatePresence>
    </div>
  );
}

function Hero({ project: p, steps }: { project: ProjectDetail; steps?: NextSteps }) {
  const { t } = useTranslation();
  const authorities = useAuthorities();
  const model = useMemo(() => sceneModel(p.build, p.floors), [p.build, p.floors]);
  const focus = useFocusLabel(model);

  return (
    <>
      <section className="relative overflow-hidden rounded-3xl border-2 border-ink shadow-[6px_6px_0_0_var(--color-ink)]">
        <LiveWorld
          className="h-[380px] w-full sm:h-[460px]"
          camera="orbit"
          model={model}
          authorities={authorities}
          focusLabel={model.complete ? undefined : focus}
          chipClassName="hidden sm:flex"
          completeLabel={t("scene.complete")}
          label={t("scene.label")}
        />
        <div className="pointer-events-none absolute inset-x-0 top-0 bg-gradient-to-b from-bg/90 via-bg/50 to-transparent p-4 pb-12 sm:p-5 sm:pb-14">
          <h1 className="font-display text-3xl font-extrabold tracking-tight sm:text-4xl">{p.name}</h1>
          <p className="text-ink-soft">{[p.address, p.municipality].filter(Boolean).join(", ")}</p>
        </div>
        <div className="absolute inset-x-0 bottom-0 flex items-end gap-2 bg-gradient-to-t from-bg/90 via-bg/50 to-transparent p-3 pt-10 sm:p-4 sm:pt-12">
          <ProgressRing done={p.build.progress.done} total={p.build.progress.total} />
          {focus && <Chip className="self-center sm:hidden">{focus}</Chip>}
          <div className="hidden flex-wrap gap-2 sm:flex">
            <HeroStats project={p} steps={steps} complete={model.complete} />
          </div>
        </div>
      </section>
      {/* On phones the stats sit under the scene instead of covering it. */}
      <div className="no-scrollbar -mx-4 -mt-3 flex gap-2 overflow-x-auto px-4 sm:hidden">
        <HeroStats project={p} steps={steps} complete={model.complete} />
      </div>
    </>
  );
}

function HeroStats({ project: p, steps, complete }: { project: ProjectDetail; steps?: NextSteps; complete: boolean }) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);
  const copyInbox = () => {
    void navigator.clipboard?.writeText(p.inbox_address).then(() => {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    });
  };
  return (
    <>
      <Chip className="shrink-0">
        ✅ {t("projects.progress", { done: p.build.progress.done, total: p.build.progress.total })}
      </Chip>
      {steps && !complete && (
        <Chip className="shrink-0">⏱️ {t("scene.daysLeft", { count: steps.critical_path.remaining_days })}</Chip>
      )}
      <button
        onClick={copyInbox}
        className="shrink-0 rounded-full border-2 border-ink bg-surface px-2.5 py-1 text-xs font-medium transition-transform hover:-translate-y-0.5 sm:px-3 sm:py-1.5 sm:text-sm"
        title={t("projects.inboxHint")}
      >
        ✉️ <span dir="ltr">{copied ? "✓" : p.inbox_address}</span>
      </button>
    </>
  );
}

function Chip({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <span
      className={cx(
        "rounded-full border-2 border-ink bg-surface px-2.5 py-1 text-xs font-bold sm:px-3 sm:py-1.5 sm:text-sm",
        className,
      )}
    >
      {children}
    </span>
  );
}

/** Animated ring with a counting percentage. */
function ProgressRing({ done, total }: { done: number; total: number }) {
  const value = total ? done / total : 0;
  const count = useMotionValue(0);
  const label = useTransform(count, (v) => `${Math.round(v)}%`);
  useEffect(() => {
    const controls = animate(count, value * 100, { duration: 1.2, ease: [0.22, 1, 0.36, 1] });
    return () => controls.stop();
  }, [count, value]);
  const r = 26;
  const circumference = 2 * Math.PI * r;
  return (
    <div className="relative grid size-16 shrink-0 place-items-center rounded-full sm:size-20 border-2 border-ink bg-surface shadow-[3px_3px_0_0_var(--color-ink)]">
      <svg viewBox="0 0 64 64" className="absolute inset-0 -rotate-90">
        <circle cx="32" cy="32" r={r} fill="none" stroke="var(--color-line)" strokeWidth="6" />
        <motion.circle
          cx="32"
          cy="32"
          r={r}
          fill="none"
          stroke="var(--color-accent)"
          strokeWidth="6"
          strokeLinecap="round"
          strokeDasharray={circumference}
          initial={{ strokeDashoffset: circumference }}
          animate={{ strokeDashoffset: circumference * (1 - value) }}
          transition={{ duration: 1.2, ease: [0.22, 1, 0.36, 1] }}
        />
      </svg>
      <motion.span className="relative font-display text-base font-extrabold sm:text-lg">{label}</motion.span>
    </div>
  );
}

/** Horizontal timeline of the template's stages; the current one pulses. */
function StageStepper({ project: p, onSelect }: { project: ProjectDetail; onSelect: (stage: string) => void }) {
  const totals = useMemo(() => {
    const map = new Map<string, { done: number; total: number }>();
    for (const s of p.build.stages) {
      const v = map.get(s.stage) ?? { done: 0, total: 0 };
      v.done += s.done;
      v.total += s.total;
      map.set(s.stage, v);
    }
    return map;
  }, [p.build.stages]);

  return (
    <div className="no-scrollbar -mx-4 overflow-x-auto px-4 pb-2">
      <ol className="flex min-w-max gap-2">
        {p.stages.map((stage, i) => {
          const v = totals.get(stage.key) ?? { done: 0, total: 0 };
          const complete = v.total > 0 && v.done === v.total;
          const current = p.build.focus_stage === stage.key;
          return (
            <motion.li
              key={stage.key}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.1 + i * 0.05 }}
            >
              <button
                onClick={() => onSelect(stage.key)}
                className={cx(
                  "relative flex w-28 flex-col items-center gap-1 overflow-hidden rounded-2xl border-2 px-2 pb-2.5 pt-2 text-center transition-all hover:-translate-y-0.5",
                  current ? "animate-pulse-ring border-ink bg-accent-soft" : complete ? "border-success/40 bg-success-soft" : "border-line bg-surface",
                )}
              >
                <span className="text-2xl">{complete ? "✅" : isStageKey(stage.key) ? STAGE_ICON[stage.key] : "•"}</span>
                <span className="text-xs font-bold leading-tight">{stage.title}</span>
                <span className="text-[11px] text-ink-soft">
                  {v.done}/{v.total}
                </span>
                <motion.span
                  className="absolute inset-x-0 bottom-0 h-1 origin-right bg-accent"
                  initial={{ scaleX: 0 }}
                  animate={{ scaleX: v.total ? v.done / v.total : 0 }}
                  transition={{ duration: 0.8 }}
                />
              </button>
            </motion.li>
          );
        })}
      </ol>
    </div>
  );
}

function NextStepsView({
  projectId,
  steps: s,
  titles,
  canEdit,
}: {
  projectId: string;
  steps: NextSteps;
  titles: ReadonlyMap<string, string>;
  canEdit: boolean;
}) {
  const { t } = useTranslation();
  const celebrate = useCelebrate();
  const fresh = useNewlyReady(s, (count) => celebrate.toast(t("toast.unlocked", { count }), "🔓"));

  if (s.progress.total > 0 && s.progress.done === s.progress.total) {
    return (
      <motion.div
        initial={{ scale: 0.9, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        className="rounded-3xl border-2 border-ink bg-accent-soft p-8 text-center font-display text-2xl font-extrabold shadow-[6px_6px_0_0_var(--color-ink)]"
      >
        🏆 {t("project.allDone")}
      </motion.div>
    );
  }

  const cards = (items: Requirement[], compact = false) => (
    <AnimatePresence mode="popLayout">
      {items.map((r, i) => (
        <RequirementCard
          key={r.id}
          layoutId={`req-${r.id}`}
          index={i}
          projectId={projectId}
          requirement={r}
          titles={titles}
          canEdit={canEdit}
          compact={compact}
          fresh={fresh.has(r.id)}
        />
      ))}
    </AnimatePresence>
  );

  return (
    <LayoutGroup id="next-steps">
      <div className="grid gap-8 lg:grid-cols-[1fr_20rem]">
        <div className="space-y-8">
          <Section title={t("project.ready")} count={s.ready.length} icon="🚀">
            {s.ready.length ? cards(s.ready) : <Empty>{t("project.readyEmpty")}</Empty>}
          </Section>
          {s.active.length > 0 && (
            <Section title={t("project.active")} count={s.active.length} icon="🔨">
              {cards(s.active)}
            </Section>
          )}
          {s.waiting.length > 0 && (
            <Section title={t("project.waiting")} count={s.waiting.length} icon="⏳">
              {cards(s.waiting)}
            </Section>
          )}
          <details className="group">
            <summary className="flex cursor-pointer list-none items-center gap-2 font-display text-xl font-bold">
              <span className="transition-transform group-open:-rotate-90">◂</span>
              🔒 {t("project.blocked")}
              <span className="text-sm font-normal text-ink-soft">({s.blocked.length})</span>
            </summary>
            <div className="mt-4 space-y-3">
              {s.blocked.length ? cards(s.blocked, true) : <Empty>{t("project.blockedEmpty")}</Empty>}
            </div>
          </details>
        </div>
        <CriticalPathCard steps={s} titles={titles} />
      </div>
    </LayoutGroup>
  );
}

/** Ids that became ready since the last refresh, reported once each. */
function useNewlyReady(steps: NextSteps, onUnlocked: (count: number) => void) {
  const previous = useRef<Set<string> | null>(null);
  const [fresh, setFresh] = useState<ReadonlySet<string>>(new Set());
  const callback = useRef(onUnlocked);
  callback.current = onUnlocked;

  useEffect(() => {
    const ready = new Set(steps.ready.map((r) => r.id));
    if (previous.current) {
      const added = [...ready].filter((id) => !previous.current!.has(id));
      if (added.length) {
        setFresh(new Set(added));
        callback.current(added.length);
      }
    }
    previous.current = ready;
  }, [steps]);
  return fresh;
}

function CriticalPathCard({ steps: s, titles }: { steps: NextSteps; titles: ReadonlyMap<string, string> }) {
  const { t } = useTranslation();
  const ids = s.critical_path.requirement_ids;
  return (
    <aside className="h-fit rounded-2xl border-2 border-ink bg-surface p-5 shadow-[5px_5px_0_0_var(--color-ink)] lg:sticky lg:top-24">
      <h2 className="font-display text-xl font-extrabold">⚡ {t("project.criticalPath")}</h2>
      <p className="mt-1 text-sm text-ink-soft">{t("project.criticalPathHint")}</p>
      <ol className="relative mt-4 space-y-2.5 border-s-2 border-dashed border-accent ps-4">
        {ids.slice(0, 8).map((id, i) => (
          <motion.li
            key={id}
            initial={{ opacity: 0, x: -12 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 0.15 + i * 0.06 }}
            className="relative text-sm"
          >
            <span
              className={cx(
                "absolute -start-[1.4rem] top-1 size-3 rounded-full border-2 border-ink",
                i === 0 ? "animate-pulse-ring bg-accent" : "bg-surface",
              )}
            />
            <span className={i === 0 ? "font-bold" : undefined}>{titles.get(id) ?? "…"}</span>
          </motion.li>
        ))}
        {ids.length > 8 && <li className="text-sm text-ink-soft">+{ids.length - 8}</li>}
      </ol>
      <p className="mt-4 rounded-xl bg-accent-soft px-3 py-2 text-sm font-bold">
        {t("project.remainingDays", { count: s.critical_path.remaining_days })}
      </p>
    </aside>
  );
}

function AllRequirementsView({
  projectId,
  stages,
  requirements,
  titles,
  canEdit,
}: {
  projectId: string;
  stages: { key: string; title: string; description?: string | null }[];
  requirements: Requirement[];
  titles: ReadonlyMap<string, string>;
  canEdit: boolean;
}) {
  return (
    <div className="space-y-10">
      {stages.map((stage) => {
        const items = requirements.filter((r) => r.stage === stage.key);
        const done = items.filter((r) => DONE_STATUSES.has(r.status as RequirementStatus)).length;
        return (
          <section key={stage.key} id={`stage-${stage.key}`} className="scroll-mt-24 space-y-3">
            <div className="flex items-end justify-between gap-3">
              <div>
                <h2 className="flex items-center gap-2 font-display text-2xl font-extrabold">
                  <span>{isStageKey(stage.key) ? STAGE_ICON[stage.key] : "•"}</span>
                  {stage.title}
                </h2>
                {stage.description && <p className="text-sm text-ink-soft">{stage.description}</p>}
              </div>
              <span className="shrink-0 rounded-full border-2 border-ink bg-surface px-3 py-1 font-display text-sm font-bold">
                {done}/{items.length}
              </span>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              {items.map((r, i) => (
                <RequirementCard
                  key={r.id}
                  index={i}
                  projectId={projectId}
                  requirement={r}
                  titles={titles}
                  canEdit={canEdit}
                  compact
                />
              ))}
            </div>
          </section>
        );
      })}
    </div>
  );
}

function Section({ title, count, icon, children }: { title: string; count: number; icon: string; children: ReactNode }) {
  return (
    <section className="space-y-3">
      <h2 className="flex items-center gap-2 font-display text-xl font-bold">
        <span>{icon}</span>
        {title}
        <span className="rounded-full bg-ink px-2 py-0.5 text-xs font-bold text-white">{count}</span>
      </h2>
      <div className="space-y-3">{children}</div>
    </section>
  );
}

function Empty({ children }: { children: ReactNode }) {
  return (
    <p className="rounded-2xl border-2 border-dashed border-line bg-surface/60 p-5 text-center text-sm text-ink-soft">
      {children}
    </p>
  );
}
