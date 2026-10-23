import type {
  ChecklistImport,
  Form4Track,
  ImportedItem,
  ProjectDetail,
  ProjectFeature,
  Requirement,
  TrackSummary,
} from "@arba/api-client";
import type { ManualStatus } from "@arba/shared";
import { AnimatePresence, motion } from "motion/react";
import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type DragEvent,
  type MouseEvent,
  type ReactNode,
} from "react";
import { useTranslation } from "react-i18next";
import { useCelebrate } from "../components/Celebrations";
import {
  Alert,
  Badge,
  Button,
  Input,
  ProgressBar,
  Spinner,
  cx,
} from "../components/ui";
import { $api, api, invalidateProjects } from "../lib/api";
import { UPLOAD_ACCEPT } from "../lib/upload";
import { useErrorMessage } from "../lib/useErrorMessage";
import { UploadProgress } from "./DocumentsView";
import { RequestForm, isProfessional } from "./TeamPanel";
import { useUploads } from "./useUploads";

const TRACK_ICON: Record<Form4Track, string> = {
  municipality: "🏛️",
  fire: "🚒",
  home_front: "🛡️",
  water: "💧",
  electricity: "⚡",
  telecom: "📡",
  gas: "🔥",
  developer: "🏗️",
  accessibility: "♿",
};

// The approving body behind each track, for items the team adds.
const TRACK_AUTHORITY = {
  municipality: "municipality",
  fire: "fire_department",
  home_front: "home_front_command",
  water: "water_corporation",
  electricity: "electrical_inspector",
  telecom: "municipality",
  gas: "gas_installer",
  developer: "municipality",
  accessibility: "municipality",
} as const satisfies Record<Form4Track, Requirement["authority_type"]>;

const FEATURES: ProjectFeature[] = [
  "basement",
  "pool",
  "elevator",
  "gas",
  "solar_heater",
  "stone_cladding",
  "retaining_walls",
  "acoustic_ceiling",
  "gypsum_ceiling",
  "steel_fences",
  "sprinklers",
  "parking",
  "commercial",
  "developer_neighborhood",
];

/** What a person sees: five plain states instead of the engine's eight. */
type FileStatus = "missing" | "working" | "fix" | "done" | "not_needed";
const FILE_STATUS: Record<Requirement["status"], FileStatus> = {
  not_started: "missing",
  blocked: "missing",
  ready: "missing",
  in_progress: "working",
  waiting_for_authority: "working",
  needs_fix: "fix",
  done: "done",
  not_applicable: "not_needed",
};
const STATUS_TARGET: Record<FileStatus, ManualStatus> = {
  missing: "not_started",
  working: "in_progress",
  fix: "needs_fix",
  done: "done",
  not_needed: "not_applicable",
};
const STATUS_STYLE: Record<FileStatus, string> = {
  missing: "border-line bg-surface text-ink-soft",
  working: "border-warning/40 bg-warning-soft text-warning",
  fix: "border-danger/40 bg-danger-soft text-danger",
  done: "border-success/40 bg-success-soft text-success",
  not_needed: "border-line bg-muted-soft text-muted",
};

const date = new Intl.DateTimeFormat("he-IL", { dateStyle: "short" });

interface Props {
  projectId: string;
  project: ProjectDetail;
  requirements: Requirement[];
  canEdit: boolean;
}

/** The Form 4 file: every document the authorities want, grouped by who wants it. */
export function Form4View({
  projectId,
  project,
  requirements,
  canEdit,
}: Props) {
  const { t } = useTranslation();
  const path = { params: { path: { project_id: projectId } } };
  const file = $api.useQuery(
    "get",
    "/api/v1/projects/{project_id}/form4",
    path,
  );
  const [hideDone, setHideDone] = useState(false);
  const titles = useMemo(
    () => new Map(requirements.map((r) => [r.id, r.title])),
    [requirements],
  );

  if (!file.data) return <Spinner label={t("app.loading")} />;
  const { tracks, done, total } = file.data;

  return (
    <div className="space-y-8">
      <header className="space-y-3">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="font-display text-3xl font-extrabold">
              📁 {t("form4.title")}
            </h2>
            <p className="max-w-2xl text-sm text-ink-soft">{t("form4.hint")}</p>
          </div>
          <button
            onClick={() => setHideDone((v) => !v)}
            className="rounded-full border-2 border-ink bg-surface px-3 py-1.5 text-sm font-bold transition-transform hover:-translate-y-0.5"
          >
            {hideDone ? t("form4.showAll") : t("form4.hideDone")}
          </button>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex-1">
            <ProgressBar done={done} total={total} />
          </div>
          <span className="shrink-0 font-display text-sm font-bold">
            {t("form4.progress", { done, total })}
          </span>
        </div>
      </header>

      <FactsCard projectId={projectId} project={project} canEdit={canEdit} />
      {canEdit && <ImportCard projectId={projectId} titles={titles} />}

      {tracks.map((summary) => (
        <TrackSection
          key={summary.track}
          projectId={projectId}
          summary={summary}
          items={requirements.filter(
            (r) => r.track === summary.track && !r.is_form4_gate,
          )}
          canEdit={canEdit}
          hideDone={hideDone}
        />
      ))}
    </div>
  );
}

/** Plot number and what the building has: the features switch documents on and off. */
function FactsCard({
  projectId,
  project: p,
  canEdit,
}: {
  projectId: string;
  project: ProjectDetail;
  canEdit: boolean;
}) {
  const { t } = useTranslation();
  const message = useErrorMessage();
  const [plot, setPlot] = useState(p.plot_number ?? "");
  useEffect(() => setPlot(p.plot_number ?? ""), [p.plot_number]);
  const update = $api.useMutation("patch", "/api/v1/projects/{project_id}", {
    onSuccess: () => invalidateProjects(),
  });
  const save = (body: {
    plot_number?: string | null;
    features?: ProjectFeature[];
  }) => update.mutate({ params: { path: { project_id: projectId } }, body });
  const features = new Set(p.features as ProjectFeature[]);
  const toggle = (feature: ProjectFeature) => {
    const next = new Set(features);
    if (next.has(feature)) next.delete(feature);
    else next.add(feature);
    save({ features: FEATURES.filter((f) => next.has(f)) });
  };

  return (
    <section className="space-y-4 rounded-2xl border-2 border-ink bg-surface p-5 shadow-[4px_4px_0_0_var(--color-ink)]">
      <div className="flex flex-wrap items-end gap-4">
        <label className="space-y-1">
          <span className="block text-sm font-medium">{t("form4.plot")}</span>
          <Input
            className="w-32"
            inputMode="numeric"
            value={plot}
            disabled={!canEdit}
            onChange={(e) => setPlot(e.target.value)}
            onBlur={() =>
              plot.trim() !== (p.plot_number ?? "") &&
              save({ plot_number: plot.trim() || null })
            }
          />
        </label>
        {p.buildings > 1 && (
          <Fact label={t("form4.buildings")} value={p.buildings} />
        )}
        {p.units != null && <Fact label={t("form4.units")} value={p.units} />}
      </div>
      <div className="space-y-2">
        <div>
          <div className="font-display text-lg font-extrabold">
            🧩 {t("form4.features")}
          </div>
          <p className="text-sm text-ink-soft">{t("form4.featuresHint")}</p>
        </div>
        <FeatureChips
          value={features}
          onToggle={toggle}
          disabled={!canEdit || update.isPending}
        />
      </div>
      {update.error && <Alert>{message(update.error)}</Alert>}
    </section>
  );
}

function Fact({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="space-y-1">
      <span className="block text-sm font-medium">{label}</span>
      <span className="block rounded-xl bg-bg px-3.5 py-3 font-display font-bold">
        {value}
      </span>
    </div>
  );
}

export function FeatureChips({
  value,
  onToggle,
  disabled,
}: {
  value: ReadonlySet<ProjectFeature>;
  onToggle: (feature: ProjectFeature) => void;
  disabled?: boolean;
}) {
  const { t } = useTranslation();
  return (
    <div className="flex flex-wrap gap-2">
      {FEATURES.map((feature) => {
        const on = value.has(feature);
        return (
          <motion.button
            key={feature}
            type="button"
            disabled={disabled}
            whileTap={{ scale: 0.94 }}
            onClick={() => onToggle(feature)}
            aria-pressed={on}
            className={cx(
              "rounded-full border-2 px-3 py-1.5 text-sm font-bold transition-colors disabled:opacity-60",
              on
                ? "border-ink bg-accent shadow-[2px_2px_0_0_var(--color-ink)]"
                : "border-line bg-surface hover:border-ink",
            )}
          >
            {on ? "✓ " : "+ "}
            {t(`feature.${feature}`)}
          </motion.button>
        );
      })}
    </div>
  );
}

function TrackSection({
  projectId,
  summary: s,
  items,
  canEdit,
  hideDone,
}: {
  projectId: string;
  summary: TrackSummary;
  items: Requirement[];
  canEdit: boolean;
  hideDone: boolean;
}) {
  const { t } = useTranslation();
  const [adding, setAdding] = useState(false);
  const shown = hideDone
    ? items.filter((r) => !["done", "not_applicable"].includes(r.status))
    : items;
  const ordered = [...shown].sort(
    (a, b) => rank(a) - rank(b) || a.order - b.order,
  );

  return (
    <section id={`track-${s.track}`} className="scroll-mt-24 space-y-3">
      <div className="flex flex-wrap items-center gap-3">
        <h3 className="flex items-center gap-2 font-display text-2xl font-extrabold">
          <span>{TRACK_ICON[s.track]}</span>
          {t(`track.${s.track}`)}
        </h3>
        <span className="rounded-full border-2 border-ink bg-surface px-3 py-0.5 font-display text-sm font-bold">
          {s.done}/{s.total}
        </span>
        {s.complete && <Badge tone="success">{t("form4.complete")}</Badge>}
        {!s.complete && s.with_files > 0 && (
          <Badge tone="info">
            📎 {t("form4.withFiles", { count: s.with_files })}
          </Badge>
        )}
      </div>
      {s.fulfils.length > 0 && (
        <p className="text-sm text-ink-soft">🔗 {t("form4.fulfils")}</p>
      )}
      <div className="h-1.5 overflow-hidden rounded-full bg-line">
        <motion.div
          className="h-full rounded-full bg-success"
          initial={{ width: 0 }}
          animate={{ width: `${s.total ? (s.done / s.total) * 100 : 0}%` }}
          transition={{ duration: 0.8 }}
        />
      </div>
      <ul className="space-y-2">
        <AnimatePresence initial={false}>
          {ordered.map((r) => (
            <Form4Row
              key={r.id}
              projectId={projectId}
              requirement={r}
              canEdit={canEdit}
            />
          ))}
        </AnimatePresence>
      </ul>
      {canEdit &&
        (adding ? (
          <AddItemForm
            projectId={projectId}
            track={s.track}
            onClose={() => setAdding(false)}
          />
        ) : (
          <button
            onClick={() => setAdding(true)}
            className="w-full rounded-2xl border-2 border-dashed border-line px-4 py-3 text-sm font-bold text-ink-soft transition-colors hover:border-ink hover:text-ink"
          >
            {t("form4.addItem")}
          </button>
        ))}
    </section>
  );
}

// Open work first, then what came in, then what isn't needed.
const rank = (r: Requirement) =>
  ({ fix: 0, missing: 1, working: 1, done: 2, not_needed: 3 })[
    FILE_STATUS[r.status]
  ];

function Form4Row({
  projectId,
  requirement: r,
  canEdit,
}: {
  projectId: string;
  requirement: Requirement;
  canEdit: boolean;
}) {
  const { t } = useTranslation();
  const message = useErrorMessage();
  const celebrate = useCelebrate();
  const [open, setOpen] = useState(false);
  const status = FILE_STATUS[r.status];
  const update = $api.useMutation(
    "patch",
    "/api/v1/projects/{project_id}/requirements/{requirement_id}/status",
    {
      onSuccess: () => invalidateProjects(),
    },
  );
  const ids = {
    params: { path: { project_id: projectId, requirement_id: r.id } },
  };

  const setStatus = (next: FileStatus, event?: MouseEvent<HTMLElement>) => {
    const rect = event?.currentTarget.getBoundingClientRect();
    update.mutate(
      { ...ids, body: { status: STATUS_TARGET[next] } },
      {
        onSuccess: () => {
          if (next === "done" && rect) {
            celebrate.burst(
              rect.left + rect.width / 2,
              rect.top + rect.height / 2,
            );
          }
        },
      },
    );
  };
  const overdue =
    r.due_date &&
    status !== "done" &&
    status !== "not_needed" &&
    new Date(r.due_date) < new Date();

  return (
    <motion.li
      layout
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, height: 0 }}
      className={cx(
        "overflow-hidden rounded-2xl border-2 bg-surface transition-colors",
        open ? "border-ink" : "border-line",
        status === "not_needed" && "opacity-60",
      )}
    >
      <div className="flex items-start gap-3 p-3">
        <button
          disabled={!canEdit || update.isPending}
          onClick={(e) => setStatus(status === "done" ? "missing" : "done", e)}
          aria-label={t(
            `form4.status.${status === "done" ? "missing" : "done"}`,
          )}
          className={cx(
            "mt-0.5 grid size-7 shrink-0 place-items-center rounded-full border-2 font-bold transition-all",
            status === "done"
              ? "border-success bg-success text-white"
              : "border-ink bg-surface hover:bg-success-soft",
            status === "not_needed" && "border-line",
          )}
        >
          {status === "done" ? "✓" : status === "not_needed" ? "–" : ""}
        </button>
        <button
          className="min-w-0 flex-1 space-y-1 text-start"
          onClick={() => setOpen((v) => !v)}
        >
          <div
            className={cx(
              "font-bold leading-snug",
              status === "not_needed" && "line-through",
            )}
          >
            {r.title}
          </div>
          <div className="flex flex-wrap items-center gap-1.5 text-xs">
            <span
              className={cx(
                "rounded-full border px-2 py-0.5 font-bold",
                STATUS_STYLE[status],
              )}
            >
              {t(`form4.status.${status}`)}
            </span>
            {r.appendix && <Badge>📄 {r.appendix}</Badge>}
            {r.standard && <Badge>📏 {r.standard}</Badge>}
            {r.document_count > 0 && (
              <Badge tone="success">
                📎 {t("form4.files", { count: r.document_count })}
              </Badge>
            )}
            {r.due_date && (
              <Badge tone={overdue ? "danger" : "neutral"}>
                📅 {date.format(new Date(r.due_date))}
              </Badge>
            )}
            {r.origin !== "template" && (
              <Badge tone="info">{t(`form4.origin.${r.origin}`)}</Badge>
            )}
            {r.check_issues.length > 0 && (
              <Badge tone="danger">🔍 {r.check_issues.length}</Badge>
            )}
          </div>
          {r.notes && <div className="text-sm text-ink-soft">💬 {r.notes}</div>}
          {r.fulfilled_by_track && (
            <div className="text-xs text-ink-soft">
              🔗{" "}
              {t("form4.fulfilledBy", {
                track: t(`track.${r.fulfilled_by_track}`),
              })}
            </div>
          )}
        </button>
        <span
          className={cx(
            "mt-1 text-ink-soft transition-transform",
            open && "-rotate-90",
          )}
        >
          ◂
        </span>
      </div>
      {update.error && (
        <div className="px-3 pb-3">
          <Alert>{message(update.error)}</Alert>
        </div>
      )}
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0 }}
            animate={{ height: "auto" }}
            exit={{ height: 0 }}
            className="overflow-hidden"
          >
            <RowDetails
              projectId={projectId}
              requirement={r}
              status={status}
              canEdit={canEdit}
              busy={update.isPending}
              onStatus={setStatus}
              onClose={() => setOpen(false)}
            />
          </motion.div>
        )}
      </AnimatePresence>
    </motion.li>
  );
}

function RowDetails({
  projectId,
  requirement: r,
  status,
  canEdit,
  busy,
  onStatus,
  onClose,
}: {
  projectId: string;
  requirement: Requirement;
  status: FileStatus;
  canEdit: boolean;
  busy: boolean;
  onStatus: (next: FileStatus, event: MouseEvent<HTMLElement>) => void;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const message = useErrorMessage();
  const ids = {
    params: { path: { project_id: projectId, requirement_id: r.id } },
  };
  const [draft, setDraft] = useState({
    notes: r.notes ?? "",
    appendix: r.appendix ?? "",
    standard: r.standard ?? "",
    due_date: r.due_date ?? "",
  });
  const edit = $api.useMutation(
    "patch",
    "/api/v1/projects/{project_id}/requirements/{requirement_id}",
    {
      onSuccess: () => invalidateProjects(),
    },
  );
  const remove = $api.useMutation(
    "delete",
    "/api/v1/projects/{project_id}/requirements/{requirement_id}",
    {
      onSuccess: () => invalidateProjects(),
    },
  );
  const uploads = useUploads(projectId);
  const fileInput = useRef<HTMLInputElement>(null);
  const [asking, setAsking] = useState(false);
  const changed =
    draft.notes !== (r.notes ?? "") ||
    draft.appendix !== (r.appendix ?? "") ||
    draft.standard !== (r.standard ?? "") ||
    draft.due_date !== (r.due_date ?? "");
  const orNull = (s: string) => s.trim() || null;
  const removable = r.origin === "user" || r.origin === "authority_list";

  return (
    <div className="space-y-3 border-t-2 border-line bg-bg/60 p-3">
      {r.description && (
        <p className="text-sm leading-relaxed">{r.description}</p>
      )}
      {r.required_documents.length > 0 && (
        <div className="flex flex-wrap gap-1.5 text-sm">
          {r.required_documents.map((d) => (
            <span
              key={d}
              className="rounded-full bg-surface px-2 py-0.5 text-ink-soft"
            >
              📎 {d}
            </span>
          ))}
        </div>
      )}
      {r.check_issues.length > 0 && (
        <div className="space-y-1 rounded-xl bg-danger-soft p-2.5 text-sm">
          <div className="font-medium">🔍 {t("checks.issuesTitle")}</div>
          {r.check_issues.map((issue) => (
            <div key={issue}>{issue}</div>
          ))}
        </div>
      )}

      {canEdit && (
        <>
          <div className="flex flex-wrap gap-1.5">
            {(Object.keys(STATUS_TARGET) as FileStatus[]).map((option) => (
              <button
                key={option}
                disabled={busy || option === status}
                onClick={(e) => onStatus(option, e)}
                className={cx(
                  "rounded-full border-2 px-3 py-1 text-sm font-bold transition-transform",
                  option === status
                    ? cx(STATUS_STYLE[option], "border-ink")
                    : "border-line bg-surface hover:-translate-y-0.5",
                )}
              >
                {t(`form4.status.${option}`)}
              </button>
            ))}
          </div>

          <div className="grid gap-2 sm:grid-cols-3">
            <SmallField label={t("form4.appendix")}>
              <Input
                value={draft.appendix}
                onChange={(e) =>
                  setDraft({ ...draft, appendix: e.target.value })
                }
              />
            </SmallField>
            <SmallField label={t("form4.standard")}>
              <Input
                value={draft.standard}
                onChange={(e) =>
                  setDraft({ ...draft, standard: e.target.value })
                }
              />
            </SmallField>
            <SmallField label={t("form4.due")}>
              <Input
                type="date"
                value={draft.due_date}
                onChange={(e) =>
                  setDraft({ ...draft, due_date: e.target.value })
                }
              />
            </SmallField>
          </div>
          <SmallField label={t("form4.notes")}>
            <Input
              placeholder={t("form4.notesPlaceholder")}
              value={draft.notes}
              onChange={(e) => setDraft({ ...draft, notes: e.target.value })}
            />
          </SmallField>
          {edit.error && <Alert>{message(edit.error)}</Alert>}
          {remove.error && <Alert>{message(remove.error)}</Alert>}
          <UploadProgress items={uploads.items} />

          <div className="flex flex-wrap gap-2">
            {changed && (
              <Button
                size="sm"
                disabled={edit.isPending}
                onClick={() =>
                  edit.mutate({
                    ...ids,
                    body: {
                      notes: orNull(draft.notes),
                      appendix: orNull(draft.appendix),
                      standard: orNull(draft.standard),
                      due_date: orNull(draft.due_date),
                    },
                  })
                }
              >
                {t("form4.save")}
              </Button>
            )}
            <Button
              size="sm"
              variant="secondary"
              disabled={uploads.busy}
              onClick={() => fileInput.current?.click()}
            >
              📎 {t("form4.attach")}
            </Button>
            {isProfessional(r.authority_type) &&
              status !== "done" &&
              !asking && (
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => setAsking(true)}
                >
                  📨{" "}
                  {t("requests.ask", {
                    role: t(`authority.${r.authority_type}`),
                  })}
                </Button>
              )}
            {removable && (
              <Button
                size="sm"
                variant="danger"
                disabled={remove.isPending}
                onClick={() => remove.mutate(ids, { onSuccess: onClose })}
              >
                {t("form4.remove")}
              </Button>
            )}
            <input
              ref={fileInput}
              type="file"
              multiple
              accept={UPLOAD_ACCEPT}
              className="hidden"
              onChange={(e) => {
                void uploads.upload([...(e.target.files ?? [])], r.id);
                e.target.value = "";
              }}
            />
          </div>
          <AnimatePresence>
            {asking && (
              <RequestForm
                projectId={projectId}
                requirement={r}
                onClose={() => setAsking(false)}
              />
            )}
          </AnimatePresence>
        </>
      )}
    </div>
  );
}

function SmallField({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <label className="block space-y-1">
      <span className="block text-xs font-medium text-ink-soft">{label}</span>
      {children}
    </label>
  );
}

function AddItemForm({
  projectId,
  track,
  onClose,
}: {
  projectId: string;
  track: Form4Track;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const message = useErrorMessage();
  const [title, setTitle] = useState("");
  const [appendix, setAppendix] = useState("");
  const [notes, setNotes] = useState("");
  const add = $api.useMutation(
    "post",
    "/api/v1/projects/{project_id}/requirements",
    {
      onSuccess: async () => {
        await invalidateProjects();
        onClose();
      },
    },
  );
  return (
    <motion.form
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="space-y-2 rounded-2xl border-2 border-ink bg-surface p-3"
      onSubmit={(e) => {
        e.preventDefault();
        if (!title.trim()) return;
        add.mutate({
          params: { path: { project_id: projectId } },
          body: {
            title: title.trim(),
            track,
            stage: "form4",
            authority_type: TRACK_AUTHORITY[track],
            documents: [],
            appendix: appendix.trim() || null,
            notes: notes.trim() || null,
          },
        });
      }}
    >
      <Input
        autoFocus
        placeholder={t("form4.addTitle")}
        value={title}
        onChange={(e) => setTitle(e.target.value)}
      />
      <div className="grid gap-2 sm:grid-cols-[10rem_1fr]">
        <Input
          placeholder={t("form4.appendix")}
          value={appendix}
          onChange={(e) => setAppendix(e.target.value)}
        />
        <Input
          placeholder={t("form4.notesPlaceholder")}
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
        />
      </div>
      {add.error && <Alert>{message(add.error)}</Alert>}
      <div className="flex gap-2">
        <Button
          size="sm"
          type="submit"
          disabled={!title.trim() || add.isPending}
        >
          {t("form4.save")}
        </Button>
        <Button size="sm" type="button" variant="ghost" onClick={onClose}>
          {t("form4.cancel")}
        </Button>
      </div>
    </motion.form>
  );
}

const LIST_ACCEPT = ".xlsx,.xlsm,.pdf,.jpg,.jpeg,.png,.webp,.txt";
type Action = "merge" | "add" | "skip";

/** An authority's own list, read and slotted in item by item; the person approves. */
function ImportCard({
  projectId,
  titles,
}: {
  projectId: string;
  titles: ReadonlyMap<string, string>;
}) {
  const { t } = useTranslation();
  const message = useErrorMessage();
  const celebrate = useCelebrate();
  const path = { params: { path: { project_id: projectId } } };
  const imports = $api.useQuery(
    "get",
    "/api/v1/projects/{project_id}/checklist/imports",
    path,
  );
  const [reading, setReading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [over, setOver] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const pending = imports.data?.find((i) => !i.applied_at);

  const read = async (file: File | undefined) => {
    if (!file) return;
    setReading(true);
    setError(null);
    const body = new FormData();
    body.append("file", file);
    const { data, error: failure } = await api.fetchClient.POST(
      "/api/v1/projects/{project_id}/checklist/imports",
      {
        ...path,
        body: body as never,
        bodySerializer: () => body,
      },
    );
    setReading(false);
    if (!data) setError(message(failure));
    await invalidateProjects();
  };

  return (
    <section className="space-y-3 rounded-2xl border-2 border-ink bg-accent-soft/50 p-5">
      <div>
        <div className="font-display text-lg font-extrabold">
          📥 {t("imports.title")}
        </div>
        <p className="text-sm">{t("imports.hint")}</p>
      </div>
      {pending ? (
        <ImportReview
          key={pending.id}
          projectId={projectId}
          imported={pending}
          titles={titles}
          onApplied={(count) =>
            celebrate.toast(`${t("imports.applied")} (${count})`, "📋")
          }
        />
      ) : (
        <>
          <motion.button
            type="button"
            disabled={reading}
            onClick={() => input.current?.click()}
            onDragOver={(e: DragEvent) => {
              e.preventDefault();
              setOver(true);
            }}
            onDragLeave={() => setOver(false)}
            onDrop={(e: DragEvent) => {
              e.preventDefault();
              setOver(false);
              void read(e.dataTransfer.files[0]);
            }}
            animate={{ scale: over ? 1.02 : 1 }}
            className={cx(
              "flex min-h-24 w-full items-center justify-center gap-3 rounded-2xl border-2 border-dashed p-4 font-bold",
              over
                ? "border-accent bg-accent-soft"
                : "border-ink/40 bg-surface hover:border-ink",
            )}
          >
            {reading ? (
              <>
                <span className="size-5 animate-spin rounded-full border-2 border-line border-t-accent" />
                {t("imports.reading")}
              </>
            ) : (
              <>
                <span className="text-2xl">📊📄📸</span>
                {t("imports.drop")}
              </>
            )}
          </motion.button>
          <input
            ref={input}
            type="file"
            accept={LIST_ACCEPT}
            className="hidden"
            onChange={(e) => {
              void read(e.target.files?.[0]);
              e.target.value = "";
            }}
          />
        </>
      )}
      {error && <Alert>{error}</Alert>}
    </section>
  );
}

function ImportReview({
  projectId,
  imported,
  titles,
  onApplied,
}: {
  projectId: string;
  imported: ChecklistImport;
  titles: ReadonlyMap<string, string>;
  onApplied: (count: number) => void;
}) {
  const { t } = useTranslation();
  const message = useErrorMessage();
  const [actions, setActions] = useState<Record<string, Action>>(() =>
    Object.fromEntries(
      imported.items.map((i) => [
        i.id,
        i.match_requirement_id ? "merge" : "add",
      ]),
    ),
  );
  const apply = $api.useMutation(
    "post",
    "/api/v1/projects/{project_id}/checklist/imports/{import_id}/apply",
    {
      onSuccess: () => invalidateProjects(),
    },
  );
  const choose = (item: ImportedItem, action: Action) =>
    setActions((a) => ({ ...a, [item.id]: action }));

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="font-bold">
          {t("imports.review", {
            count: imported.items.length,
            file: imported.file_name,
          })}
        </span>
        <Badge tone="info">
          ✨{" "}
          {t(
            `imports.readBy.${imported.source === "claude" ? "claude" : "rules"}`,
          )}
        </Badge>
      </div>
      <ul className="max-h-[28rem] space-y-1.5 overflow-y-auto pe-1">
        {imported.items.map((item) => {
          const action = actions[item.id] ?? "add";
          const options: Action[] = item.match_requirement_id
            ? ["merge", "add", "skip"]
            : ["add", "skip"];
          return (
            <li
              key={item.id}
              className={cx(
                "rounded-xl border-2 bg-surface p-2.5 text-sm",
                action === "skip" ? "border-line opacity-60" : "border-ink/30",
              )}
            >
              <div className="flex flex-wrap items-start gap-2">
                <div className="min-w-0 flex-1 space-y-1">
                  <div className="font-bold">
                    {item.number && (
                      <span className="text-ink-soft">{item.number}. </span>
                    )}
                    {item.title}
                  </div>
                  <div className="flex flex-wrap gap-1.5 text-xs">
                    <Badge>
                      {TRACK_ICON[item.track]} {t(`track.${item.track}`)}
                    </Badge>
                    {item.appendix && <Badge>📄 {item.appendix}</Badge>}
                    {item.standard && <Badge>📏 {item.standard}</Badge>}
                    {item.not_needed && (
                      <Badge tone="muted">{t("imports.notNeeded")}</Badge>
                    )}
                    {item.notes && <Badge>💬 {item.notes}</Badge>}
                  </div>
                  <div className="text-xs text-ink-soft">
                    {action === "merge" && item.match_requirement_id
                      ? `🔗 ${t("imports.merge", { title: item.match_title ?? titles.get(item.match_requirement_id) ?? "…" })}`
                      : action === "add"
                        ? `✨ ${t("imports.add")}`
                        : `⏭️ ${t("imports.skip")}`}
                  </div>
                </div>
                <div className="flex shrink-0 gap-1">
                  {options.map((option) => (
                    <button
                      key={option}
                      onClick={() => choose(item, option)}
                      className={cx(
                        "rounded-full border-2 px-2.5 py-1 text-xs font-bold",
                        option === action
                          ? "border-ink bg-ink text-white"
                          : "border-line bg-surface hover:border-ink",
                      )}
                    >
                      {t(`imports.actions.${option}`)}
                    </button>
                  ))}
                </div>
              </div>
            </li>
          );
        })}
      </ul>
      {apply.error && <Alert>{message(apply.error)}</Alert>}
      <div className="flex flex-wrap gap-2">
        <Button
          disabled={apply.isPending}
          onClick={() =>
            apply.mutate(
              {
                params: {
                  path: { project_id: projectId, import_id: imported.id },
                },
                body: {
                  decisions: imported.items.map((item) => ({
                    item_id: item.id,
                    action: actions[item.id] ?? "add",
                    requirement_id:
                      actions[item.id] === "merge"
                        ? item.match_requirement_id
                        : null,
                  })),
                },
              },
              {
                onSuccess: () =>
                  onApplied(
                    Object.values(actions).filter((a) => a !== "skip").length,
                  ),
              },
            )
          }
        >
          ✓ {t("imports.apply")}
        </Button>
        <Button
          variant="ghost"
          disabled={apply.isPending}
          onClick={() =>
            apply.mutate({
              params: {
                path: { project_id: projectId, import_id: imported.id },
              },
              body: {
                decisions: imported.items.map((item) => ({
                  item_id: item.id,
                  action: "skip" as const,
                })),
              },
            })
          }
        >
          {t("imports.discard")}
        </Button>
      </div>
    </div>
  );
}
