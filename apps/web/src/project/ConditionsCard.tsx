import type { PermitCondition } from "@arba/api-client";
import { AnimatePresence, motion } from "motion/react";
import { useTranslation } from "react-i18next";
import { useCelebrate } from "../components/Celebrations";
import { Alert, Badge, Button, cx } from "../components/ui";
import { $api, invalidateProjects } from "../lib/api";
import { useErrorMessage } from "../lib/useErrorMessage";
import { isStageKey } from "../scene/model";

const CONDITIONS = "/api/v1/projects/{project_id}/permit/conditions";

/** The permit's own conditions: Arba proposes where each goes, the person approves. */
export function ConditionsCard({ projectId, canEdit }: { projectId: string; canEdit: boolean }) {
  const { t } = useTranslation();
  const message = useErrorMessage();
  const { toast, burst } = useCelebrate();
  const path = { params: { path: { project_id: projectId } } };
  const list = $api.useQuery("get", CONDITIONS, path, {
    refetchInterval: (q) => (q.state.data?.status === "reading" ? 2000 : false),
  });
  const done = { onSuccess: () => void invalidateProjects() };
  const acceptAll = $api.useMutation("post", `${CONDITIONS}/accept-all`, done);
  const accept = $api.useMutation("post", `${CONDITIONS}/{condition_id}/accept`, done);
  const ignore = $api.useMutation("post", `${CONDITIONS}/{condition_id}/ignore`, done);
  const reread = $api.useMutation("post", `${CONDITIONS}/read`, done);

  const data = list.data;
  if (!data?.status) return null;
  const proposed = data.conditions.filter((c) => c.status === "proposed");
  const decided = data.conditions.filter((c) => c.status !== "proposed");
  // Once everything is decided, the steps themselves carry the conditions.
  if (data.status === "ready" && proposed.length === 0) return null;
  const error = acceptAll.error ?? accept.error ?? ignore.error;

  return (
    <motion.section
      layout
      initial={{ opacity: 0, y: -8 }}
      animate={{ opacity: 1, y: 0 }}
      className="space-y-3 rounded-2xl border-2 border-ink bg-surface p-4 shadow-[4px_4px_0_0_var(--color-ink)] sm:p-5"
    >
      <div className="flex flex-wrap items-start gap-3">
        <span className="text-3xl">📜</span>
        <div className="min-w-0 flex-1">
          <h2 className="font-display text-xl font-extrabold">{t("conditions.title")}</h2>
          <p className="text-sm text-ink-soft">{t("conditions.hint")}</p>
        </div>
        {canEdit && proposed.length > 1 && (
          <Button
            disabled={acceptAll.isPending}
            onClick={(e) => {
              const r = e.currentTarget.getBoundingClientRect();
              acceptAll.mutate(path, {
                onSuccess: () => {
                  burst(r.left + r.width / 2, r.top);
                  toast(t("conditions.added", { count: proposed.length }), "📜");
                },
              });
            }}
          >
            ✓ {t("conditions.approveAll", { count: proposed.length })}
          </Button>
        )}
      </div>

      {data.status === "reading" && <Reading />}
      {data.status === "failed" && (
        <div className="flex flex-wrap items-center gap-3">
          <Alert tone="warning">{t("conditions.failed")}</Alert>
          {canEdit && (
            <Button size="sm" variant="secondary" onClick={() => reread.mutate(path)}>
              {t("conditions.retry")}
            </Button>
          )}
        </div>
      )}
      {data.status === "ready" && data.conditions.length === 0 && (
        <p className="text-sm text-ink-soft">{t("conditions.none")}</p>
      )}
      {error && <Alert>{message(error)}</Alert>}

      <ul className="space-y-2">
        <AnimatePresence initial={false}>
          {proposed.map((c, i) => (
            <ConditionRow
              key={c.id}
              condition={c}
              index={i}
              canEdit={canEdit}
              busy={accept.isPending || ignore.isPending}
              onAccept={(asNew) =>
                accept.mutate({
                  params: { path: { project_id: projectId, condition_id: c.id } },
                  body: { as_new: asNew },
                })
              }
              onIgnore={() =>
                ignore.mutate({ params: { path: { project_id: projectId, condition_id: c.id } } })
              }
            />
          ))}
        </AnimatePresence>
      </ul>
      {decided.length > 0 && (
        <p className="text-xs text-ink-soft">
          ✓{" "}
          {decided
            .filter((c) => c.status === "accepted")
            .map((c) => c.title)
            .join(" · ")}
        </p>
      )}
    </motion.section>
  );
}

function ConditionRow({
  condition: c,
  index,
  canEdit,
  busy,
  onAccept,
  onIgnore,
}: {
  condition: PermitCondition;
  index: number;
  canEdit: boolean;
  busy: boolean;
  onAccept: (asNew: boolean) => void;
  onIgnore: () => void;
}) {
  const { t } = useTranslation();
  const linked = c.match_requirement_id !== null;
  return (
    <motion.li
      layout
      initial={{ opacity: 0, x: 20 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: -40, height: 0 }}
      transition={{ delay: index * 0.05 }}
      className="space-y-2 rounded-xl border-2 border-line bg-bg p-3"
    >
      <div className="flex flex-wrap items-center gap-1.5">
        {c.number && <Badge>{t("conditions.section", { number: c.number })}</Badge>}
        <Badge tone="warning">{t(`conditions.timing.${c.timing}`)}</Badge>
        <Badge tone="info">{t(`authority.${c.authority_type}`)}</Badge>
      </div>
      <div className="font-bold">{c.title}</div>
      <p className="text-sm text-ink-soft">“{c.text}”</p>
      <div
        className={cx(
          "rounded-lg px-2.5 py-1.5 text-sm font-medium",
          linked ? "bg-info-soft text-info" : "bg-accent-soft",
        )}
      >
        🤖{" "}
        {linked
          ? t("conditions.addTo", { title: c.requirement_title ?? "" })
          : t("conditions.newStep", { stage: isStageKey(c.stage) ? t(`stage.${c.stage}`) : c.stage })}
        {c.documents.length > 0 && ` · 📎 ${c.documents.join(", ")}`}
      </div>
      {canEdit && (
        <div className="flex flex-wrap gap-2">
          <Button size="sm" disabled={busy} onClick={() => onAccept(false)}>
            ✓ {t("conditions.approve")}
          </Button>
          {linked && (
            <Button size="sm" variant="secondary" disabled={busy} onClick={() => onAccept(true)}>
              {t("conditions.makeNew")}
            </Button>
          )}
          <Button size="sm" variant="ghost" disabled={busy} onClick={onIgnore}>
            {t("conditions.ignore")}
          </Button>
        </div>
      )}
    </motion.li>
  );
}

function Reading() {
  const { t } = useTranslation();
  return (
    <div className="flex items-center gap-4 rounded-xl bg-accent-soft p-4">
      <div className="relative h-16 w-12 overflow-hidden rounded-md border-2 border-ink bg-surface">
        {[...Array(5)].map((_, i) => (
          <span key={i} className="mx-1.5 mt-2 block h-1 rounded bg-line" style={{ width: `${50 + ((i * 19) % 40)}%` }} />
        ))}
        <motion.span
          className="absolute inset-x-0 h-4 bg-gradient-to-b from-transparent via-accent/70 to-transparent"
          animate={{ top: ["-20%", "100%"] }}
          transition={{ duration: 1.3, repeat: Infinity, ease: "linear" }}
        />
      </div>
      <span className="font-display font-bold">{t("conditions.reading")}</span>
    </div>
  );
}
