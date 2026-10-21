import type { Requirement, Stage, Suggestion } from "@arba/api-client";
import { STATUS_TONE, type RequirementStatus } from "@arba/shared";
import { AnimatePresence, motion } from "motion/react";
import { useState, type MouseEvent } from "react";
import { useTranslation } from "react-i18next";
import { useCelebrate } from "../components/Celebrations";
import { Alert, Badge, Button, cx } from "../components/ui";
import { $api, invalidateProjects } from "../lib/api";
import { useErrorMessage } from "../lib/useErrorMessage";
import { RequirementPicker } from "./RequirementPicker";

const KIND_ICON: Record<Suggestion["kind"], string> = {
  approval: "✅",
  rejection: "❌",
  request_for_info: "📝",
  info: "ℹ️",
  other: "📨",
};

interface Props {
  projectId: string;
  suggestion: Suggestion;
  stages: Stage[];
  requirements: Requirement[];
  canEdit: boolean;
  /** Inside a thread or document view: the item itself is already on screen. */
  compact?: boolean;
}

/** Arba's proposal for one email or file, approved with one tap or changed first. */
export function SuggestionCard({ projectId, suggestion: s, stages, requirements, canEdit, compact }: Props) {
  const { t } = useTranslation();
  const message = useErrorMessage();
  const celebrate = useCelebrate();
  const unsure = !s.requirement_id;
  const [changing, setChanging] = useState(unsure);
  const [choice, setChoice] = useState<string | null>(s.requirement_id);
  const [showReason, setShowReason] = useState(false);
  const path = { project_id: projectId, suggestion_id: s.id };

  const accept = $api.useMutation("post", "/api/v1/projects/{project_id}/suggestions/{suggestion_id}/accept");
  const dismiss = $api.useMutation("post", "/api/v1/projects/{project_id}/suggestions/{suggestion_id}/dismiss", {
    onSuccess: () => void invalidateProjects(),
  });

  const approve = (event: MouseEvent<HTMLButtonElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    const changed = choice !== s.requirement_id;
    accept.mutate(
      {
        params: { path },
        body: changed ? { requirement_id: choice, apply_status: true } : { apply_status: true },
      },
      {
        onSuccess: (result) => {
          celebrate.burst(rect.left + rect.width / 2, rect.top + rect.height / 2);
          celebrate.toast(
            result.status_error
              ? t("suggestions.filedNoStatus", { reason: message(result.status_error) })
              : t("suggestions.doneToast"),
            result.status_error ? "🗂️" : "🎉",
          );
          void invalidateProjects();
        },
      },
    );
  };

  const busy = accept.isPending || dismiss.isPending;
  const sure = s.confidence >= 0.7;

  return (
    <motion.article
      layout
      initial={{ opacity: 0, y: 16, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, x: 60, transition: { duration: 0.3 } }}
      className={cx(
        "relative space-y-3 overflow-hidden rounded-2xl border-2 border-ink bg-surface p-4",
        compact ? "shadow-[3px_3px_0_0_var(--color-accent)]" : "shadow-[5px_5px_0_0_var(--color-accent)]",
      )}
    >
      {/* A slow shimmer along the top edge: this card was prepared by Arba. */}
      <motion.span
        aria-hidden
        className="absolute inset-x-0 top-0 h-1 bg-gradient-to-l from-accent via-amber-200 to-accent"
        animate={{ backgroundPositionX: ["0%", "200%"] }}
        transition={{ duration: 3, repeat: Infinity, ease: "linear" }}
        style={{ backgroundSize: "200% 100%" }}
      />

      {!compact && (
        <div className="flex items-start gap-3">
          <span className="grid size-11 shrink-0 place-items-center rounded-xl border-2 border-ink bg-accent-soft text-xl">
            {KIND_ICON[s.kind]}
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-1.5 text-xs text-ink-soft">
              <span className="font-bold text-ink">{t(`suggestions.kind.${s.kind}`)}</span>
              <span>·</span>
              <span>
                {s.target === "thread"
                  ? t("suggestions.fromEmail", { sender: s.sender ?? "" })
                  : t("suggestions.upload")}
              </span>
              {s.file_count > 0 && s.target === "thread" && (
                <span>· 📎 {t("suggestions.files", { count: s.file_count })}</span>
              )}
            </div>
            <h3 className="truncate font-display text-lg font-bold">{s.title}</h3>
          </div>
        </div>
      )}

      <p className="text-[15px] leading-relaxed">✨ {s.summary}</p>

      {!unsure && !changing && (
        <div className="flex flex-wrap items-center gap-x-1.5 gap-y-1 rounded-xl bg-bg px-3 py-2 text-sm">
          <span>{t("suggestions.fileUnder")}</span>
          <span className="font-bold">“{s.requirement_title}”</span>
          {s.suggested_status && (
            <>
              <span>{t("suggestions.andMark")}</span>
              <Badge tone={STATUS_TONE[s.suggested_status as RequirementStatus]}>
                {t(`status.${s.suggested_status as RequirementStatus}`)}
              </Badge>
            </>
          )}
        </div>
      )}

      <AnimatePresence initial={false}>
        {changing && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="space-y-1.5 overflow-hidden"
          >
            {unsure && <p className="text-sm font-medium">{t("suggestions.unsure")}</p>}
            <RequirementPicker
              stages={stages}
              requirements={requirements}
              value={choice}
              onChange={setChoice}
              disabled={!canEdit || busy}
              className="w-full"
            />
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence initial={false}>
        {showReason && (
          <motion.p
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="overflow-hidden text-sm text-ink-soft"
          >
            💡 {s.reason}
          </motion.p>
        )}
      </AnimatePresence>

      {(accept.error || dismiss.error) && <Alert>{message(accept.error ?? dismiss.error)}</Alert>}

      {canEdit && (
        <div className="flex flex-wrap items-center gap-2">
          <Button className="min-w-32 flex-1 sm:flex-none" disabled={busy || !choice} onClick={approve}>
            ✓ {changing && choice !== s.requirement_id ? t("suggestions.approveChoice") : t("suggestions.approve")}
          </Button>
          {!changing && (
            <Button variant="secondary" size="sm" disabled={busy} onClick={() => setChanging(true)}>
              {t("suggestions.change")}
            </Button>
          )}
          <button
            className="rounded-full px-2 py-1 text-sm font-medium text-ink-soft hover:text-ink"
            onClick={() => setShowReason((v) => !v)}
          >
            {t("suggestions.why")}
          </button>
          <span
            className={cx(
              "ms-auto rounded-full px-2 py-0.5 text-xs font-bold",
              sure ? "bg-success-soft text-success" : "bg-warning-soft text-warning",
            )}
          >
            {sure ? t("suggestions.sure") : t("suggestions.check")}
          </span>
          <button
            aria-label={t("suggestions.dismiss")}
            title={t("suggestions.dismiss")}
            disabled={busy}
            onClick={() => dismiss.mutate({ params: { path } })}
            className="grid size-8 place-items-center rounded-full text-ink-soft hover:bg-bg hover:text-ink"
          >
            ✕
          </button>
        </div>
      )}
    </motion.article>
  );
}

/** The "waiting for you" stack at the top of the project page. */
export function ApprovalsPanel({
  projectId,
  suggestions,
  stages,
  requirements,
  canEdit,
}: Omit<Props, "suggestion" | "compact"> & { suggestions: Suggestion[] }) {
  const { t } = useTranslation();
  return (
    <AnimatePresence>
      {suggestions.length > 0 && (
        <motion.section
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, height: 0, marginBottom: 0 }}
          className="space-y-3"
        >
          <div>
            <h2 className="flex items-center gap-2 font-display text-xl font-extrabold">
              <motion.span
                animate={{ rotate: [0, 15, -10, 0], scale: [1, 1.15, 1] }}
                transition={{ duration: 2.2, repeat: Infinity, repeatDelay: 1.5 }}
              >
                ✨
              </motion.span>
              {t("suggestions.title")}
              <span className="rounded-full bg-accent px-2 py-0.5 text-xs font-bold text-ink">
                {suggestions.length}
              </span>
            </h2>
            <p className="text-sm text-ink-soft">{t("suggestions.subtitle")}</p>
          </div>
          <div className="space-y-3">
            <AnimatePresence mode="popLayout">
              {suggestions.map((s) => (
                <SuggestionCard
                  key={s.id}
                  projectId={projectId}
                  suggestion={s}
                  stages={stages}
                  requirements={requirements}
                  canEdit={canEdit}
                />
              ))}
            </AnimatePresence>
          </div>
        </motion.section>
      )}
    </AnimatePresence>
  );
}
