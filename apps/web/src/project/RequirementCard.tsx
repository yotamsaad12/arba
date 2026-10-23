import type { Requirement } from "@arba/api-client";
import { STATUS_TONE, statusActions, type ManualStatus, type RequirementStatus } from "@arba/shared";
import { AnimatePresence, motion } from "motion/react";
import { useRef, useState, type MouseEvent } from "react";
import { useTranslation } from "react-i18next";
import { useCelebrate } from "../components/Celebrations";
import { Alert, Badge, Button, cx } from "../components/ui";
import { $api, invalidateProjects } from "../lib/api";
import { UPLOAD_ACCEPT } from "../lib/upload";
import { useErrorMessage } from "../lib/useErrorMessage";
import { UploadProgress } from "./DocumentsView";
import { RequestForm, isProfessional } from "./TeamPanel";
import { useUploads } from "./useUploads";

// The approving bodies Arba writes to (mirrors WRITES_TO in backend/app/modules/outreach).
const WRITES_TO = new Set(["municipality", "water_corporation", "fire_department", "home_front_command"]);

interface Props {
  projectId: string;
  requirement: Requirement;
  titles: ReadonlyMap<string, string>;
  canEdit: boolean;
  compact?: boolean;
  /** Just unlocked: glow briefly so the eye finds it. */
  fresh?: boolean;
  /** Shared across sections, so a card glides from "ready" to "in progress". */
  layoutId?: string;
  index?: number;
}

export function RequirementCard({
  projectId,
  requirement: r,
  titles,
  canEdit,
  compact,
  fresh,
  layoutId,
  index = 0,
}: Props) {
  const { t } = useTranslation();
  const message = useErrorMessage();
  const celebrate = useCelebrate();
  const update = $api.useMutation(
    "patch",
    "/api/v1/projects/{project_id}/requirements/{requirement_id}/status",
    { onSuccess: () => invalidateProjects() },
  );

  const write = $api.useMutation("post", "/api/v1/projects/{project_id}/requirements/{requirement_id}/drafts", {
    onSuccess: async () => {
      await invalidateProjects();
      document.getElementById("drafts")?.scrollIntoView({ behavior: "smooth", block: "start" });
    },
  });
  const canWrite = canEdit && WRITES_TO.has(r.authority_type) && !["done", "not_applicable"].includes(r.status);

  const [asking, setAsking] = useState(false);
  const canAsk = canEdit && isProfessional(r.authority_type) && !["done", "not_applicable"].includes(r.status);

  const uploads = useUploads(projectId);
  const fileInput = useRef<HTMLInputElement>(null);

  const status = r.status as RequirementStatus;
  const started = !["not_started", "ready", "blocked"].includes(status);
  const actions = canEdit ? statusActions(status, r.optional) : [];

  const setStatus = (next: ManualStatus, event: MouseEvent<HTMLButtonElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    update.mutate(
      {
        params: { path: { project_id: projectId, requirement_id: r.id } },
        body: { status: next },
      },
      {
        onSuccess: () => {
          if (next === "done") {
            celebrate.burst(rect.left + rect.width / 2, rect.top + rect.height / 2);
            celebrate.toast(t("toast.done"), "🎉");
          }
        },
      },
    );
  };

  return (
    <motion.article
      layout
      layoutId={layoutId}
      initial={{ opacity: 0, y: 16 }}
      animate={{
        opacity: 1,
        y: 0,
        boxShadow: fresh
          ? ["0 0 0 0 rgb(245 158 11 / 0.7)", "0 0 0 10px rgb(245 158 11 / 0)", "0 0 0 0 rgb(245 158 11 / 0)"]
          : undefined,
      }}
      exit={{ opacity: 0, scale: 0.96, transition: { duration: 0.2 } }}
      transition={{
        layout: { type: "spring", stiffness: 300, damping: 30 },
        default: { duration: 0.45, delay: Math.min(index, 8) * 0.04, ease: [0.22, 1, 0.36, 1] },
        boxShadow: { duration: 1.4, repeat: fresh ? 2 : 0 },
      }}
      className={cx(
        "relative space-y-3 overflow-hidden rounded-2xl border-2 bg-surface p-4 transition-colors",
        r.on_critical_path ? "border-ink shadow-[4px_4px_0_0_var(--color-ink)]" : "border-line",
        status === "done" && "bg-success-soft/40",
      )}
    >
      {r.on_critical_path && <span className="absolute inset-y-0 start-0 w-1.5 bg-accent" aria-hidden />}

      <div className="space-y-1.5">
        <div className="flex flex-wrap items-center gap-1.5">
          <Badge tone={STATUS_TONE[status]}>{t(`status.${status}`)}</Badge>
          {r.on_critical_path && <Badge tone="warning">⚡ {t("requirement.criticalPath")}</Badge>}
          {r.optional && <Badge>{t("requirement.optional")}</Badge>}
          {r.origin !== "template" && <Badge tone="info">📜 {t(`origin.${r.origin}`)}</Badge>}
          {r.document_count > 0 && (
            <Badge tone="success">📎 {t("documents.count", { count: r.document_count })}</Badge>
          )}
        </div>
        <h3 className="font-display text-lg font-bold leading-snug">{r.title}</h3>
        <p className="text-sm text-ink-soft">
          {t(`authority.${r.authority_type}`)} · {t(`channel.${r.channel}`)} ·{" "}
          {t("requirement.days", { count: r.estimated_days })}
        </p>
      </div>

      {!compact && r.description && <p className="text-sm leading-relaxed">{r.description}</p>}

      {r.blocked_by.length > 0 && (
        <div className={cx("rounded-xl p-2.5 text-sm", started ? "bg-danger-soft" : "bg-bg")}>
          <div className="font-medium">
            {started ? t("requirement.regressed") : t("requirement.blockedBy")}
          </div>
          <ul className="mt-1 list-disc space-y-0.5 ps-5">
            {r.blocked_by.map((id) => (
              <li key={id}>{titles.get(id) ?? "…"}</li>
            ))}
          </ul>
        </div>
      )}

      {!compact && r.required_documents.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5 text-sm">
          <span className="font-medium">📎 {t("requirement.documents")}:</span>
          {r.required_documents.map((d) => (
            <span key={d} className="rounded-full bg-bg px-2 py-0.5 text-ink-soft">
              {d}
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

      {update.error && <Alert>{message(update.error)}</Alert>}
      {write.error && <Alert>{message(write.error)}</Alert>}
      <UploadProgress items={uploads.items} />

      {(actions.length > 0 || canEdit) && (
        <div className="flex flex-wrap gap-2 pt-1">
          {actions.map((next, i) => (
            <Button
              key={next}
              size="sm"
              variant={next === "needs_fix" ? "danger" : i === 0 ? "primary" : "secondary"}
              disabled={update.isPending}
              onClick={(e) => setStatus(next, e)}
            >
              {next === "done" && "✓ "}
              {t(`requirement.action.${next}`)}
            </Button>
          ))}
          {canEdit && (
            <>
              <Button
                size="sm"
                variant="ghost"
                disabled={uploads.busy}
                onClick={() => fileInput.current?.click()}
              >
                📎 {t("documents.attach")}
              </Button>
              {canAsk && !asking && (
                <Button size="sm" variant="ghost" onClick={() => setAsking(true)}>
                  📨 {t("requests.ask", { role: t(`authority.${r.authority_type}`) })}
                </Button>
              )}
              {canWrite && (
                <Button
                  size="sm"
                  variant="ghost"
                  disabled={write.isPending}
                  onClick={() =>
                    write.mutate({
                      params: { path: { project_id: projectId, requirement_id: r.id } },
                      body: { kind: "request" },
                    })
                  }
                >
                  ✉️ {write.isPending ? t("drafts.writing") : t("drafts.write")}
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
            </>
          )}
        </div>
      )}
      <AnimatePresence>
        {asking && <RequestForm projectId={projectId} requirement={r} onClose={() => setAsking(false)} />}
      </AnimatePresence>
    </motion.article>
  );
}
