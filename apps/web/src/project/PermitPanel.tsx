import type { AuthorityInfo, PermitInfo } from "@arba/api-client";
import { AnimatePresence, motion } from "motion/react";
import { useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { useCelebrate } from "../components/Celebrations";
import { Alert, Badge, Button, Field, Input, cx } from "../components/ui";
import { $api, api, invalidateProjects } from "../lib/api";
import { uploadFile } from "../lib/upload";
import { useErrorMessage } from "../lib/useErrorMessage";

const STATUS_STYLE = {
  pending_verification: { icon: "⏳", tone: "bg-warning-soft" },
  needs_attention: { icon: "⚠️", tone: "bg-danger-soft" },
  document_checked: { icon: "🔍", tone: "bg-accent-soft" },
  committee_confirmed: { icon: "✅", tone: "bg-success-soft" },
} as const;

/** The permit gate: what's verified, what's missing, and the one action that moves it forward. */
export function PermitBanner({
  projectId,
  permit,
  canEdit,
}: {
  projectId: string;
  permit: PermitInfo;
  canEdit: boolean;
}) {
  const { t } = useTranslation();
  const message = useErrorMessage();
  const { toast, burst } = useCelebrate();
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const path = { params: { path: { project_id: projectId } } };
  const style = STATUS_STYLE[permit.status];
  const [open, setOpen] = useState(permit.status !== "committee_confirmed");

  const run = async (work: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await work();
    } catch (e) {
      setError(message(e));
    }
    await invalidateProjects();
    setBusy(false);
  };

  const upload = (file: File) =>
    run(async () => {
      await uploadFile(projectId, file, permit.requirement_id, () => {});
      const { error: failure } = await api.fetchClient.POST("/api/v1/projects/{project_id}/permit/check", path);
      if (failure) throw failure;
    });

  const confirm = () =>
    run(async () => {
      const { error: failure } = await api.fetchClient.POST("/api/v1/projects/{project_id}/permit/confirm", path);
      if (failure) throw failure;
      toast(t("permit.confirmedToast"), "🏛️");
      burst(window.innerWidth / 2, window.innerHeight / 3);
    });

  const hint = {
    pending_verification: t("permit.pendingHint"),
    needs_attention: t("permit.attentionHint"),
    document_checked: t("permit.checkedHint"),
    committee_confirmed: null,
  }[permit.status];

  return (
    <motion.section
      layout
      initial={{ opacity: 0, y: -10 }}
      animate={{ opacity: 1, y: 0 }}
      className={cx("rounded-2xl border-2 border-ink p-4 shadow-[4px_4px_0_0_var(--color-ink)] sm:p-5", style.tone)}
    >
      <button type="button" className="flex w-full items-center gap-3 text-start" onClick={() => setOpen(!open)}>
        <motion.span
          className="text-3xl"
          animate={permit.status === "pending_verification" ? { rotate: [0, 180, 180, 360] } : {}}
          transition={{ duration: 2.4, repeat: Infinity, times: [0, 0.2, 0.8, 1] }}
        >
          {style.icon}
        </motion.span>
        <span className="min-w-0 flex-1">
          <span className="block font-display text-lg font-extrabold">{t(`permit.status.${permit.status}`)}</span>
          <span className="block truncate text-sm text-ink-soft">
            {[permit.number && `${t("permit.number")} ${permit.number}`, permit.official_committee]
              .filter(Boolean)
              .join(" · ")}
          </span>
        </span>
        <span className="text-ink-soft">{open ? "▲" : "▼"}</span>
      </button>

      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="overflow-hidden"
          >
            <div className="space-y-4 pt-4">
              {hint && <p className="text-sm font-medium">{hint}</p>}
              <ul className="grid gap-1.5 sm:grid-cols-2">
                {permit.checks.map((c, i) => (
                  <motion.li
                    key={c.check}
                    initial={{ opacity: 0, x: 10 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: i * 0.07 }}
                    className="flex items-start gap-2 rounded-lg bg-surface/70 px-3 py-2 text-sm"
                  >
                    <span>{c.ok === true ? "✅" : c.ok === false ? "❌" : "➖"}</span>
                    <span>{c.message}</span>
                  </motion.li>
                ))}
              </ul>

              {canEdit && editing && (
                <PermitEditor
                  projectId={projectId}
                  permit={permit}
                  onDone={() => setEditing(false)}
                />
              )}
              {error && <Alert>{error}</Alert>}

              {canEdit && (
                <div className="flex flex-wrap gap-2">
                  {permit.status === "pending_verification" && (
                    <Button disabled={busy} onClick={() => input.current?.click()}>
                      📜 {busy ? t("permit.reading") : t("permit.uploadPermit")}
                    </Button>
                  )}
                  {permit.search_url && permit.status !== "committee_confirmed" && (
                    <Button variant="secondary" onClick={() => window.open(permit.search_url!, "_blank", "noopener")}>
                      🔎 {t("permit.openCommitteeSearch")}
                    </Button>
                  )}
                  {!permit.search_url && permit.committee_website && permit.status !== "committee_confirmed" && (
                    <Button variant="secondary" onClick={() => window.open(permit.committee_website!, "_blank", "noopener")}>
                      🏛️ {t("permit.openCommitteeSite")}
                    </Button>
                  )}
                  {(permit.status === "document_checked" || permit.status === "needs_attention") && (
                    <Button disabled={busy} variant={permit.status === "document_checked" ? "primary" : "secondary"} onClick={() => void confirm()}>
                      ✓ {t("permit.confirm")}
                    </Button>
                  )}
                  {!editing && (
                    <Button variant="ghost" onClick={() => setEditing(true)}>
                      ✏️ {t("permit.edit")}
                    </Button>
                  )}
                </div>
              )}
              <input
                ref={input}
                type="file"
                accept="application/pdf,.pdf"
                className="hidden"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  e.target.value = "";
                  if (file) void upload(file);
                }}
              />
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.section>
  );
}

interface EditValues {
  permit_number: string;
  permit_request_number: string;
  permit_issue_date: string;
  permit_valid_until: string;
  permit_committee: string;
}

function PermitEditor({ projectId, permit, onDone }: { projectId: string; permit: PermitInfo; onDone: () => void }) {
  const { t } = useTranslation();
  const message = useErrorMessage();
  const save = $api.useMutation("patch", "/api/v1/projects/{project_id}/permit");
  const form = useForm<EditValues>({
    defaultValues: {
      permit_number: permit.number ?? "",
      permit_request_number: permit.request_number ?? "",
      permit_issue_date: permit.issue_date ?? "",
      permit_valid_until: permit.valid_until ?? "",
      permit_committee: permit.committee_on_permit ?? "",
    },
  });
  const submit = form.handleSubmit((v) => {
    const orNull = (s: string) => s.trim() || null;
    save.mutate(
      {
        params: { path: { project_id: projectId } },
        body: {
          permit_number: orNull(v.permit_number),
          permit_request_number: orNull(v.permit_request_number),
          permit_issue_date: orNull(v.permit_issue_date),
          permit_valid_until: orNull(v.permit_valid_until),
          permit_committee: orNull(v.permit_committee),
        },
      },
      {
        onSuccess: () => {
          void invalidateProjects();
          onDone();
        },
      },
    );
  });
  return (
    <form className="space-y-3 rounded-xl bg-surface p-4" onSubmit={(e) => void submit(e)}>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label={t("permit.number")}>
          <Input dir="ltr" {...form.register("permit_number")} />
        </Field>
        <Field label={t("permit.requestNumber")}>
          <Input dir="ltr" {...form.register("permit_request_number")} />
        </Field>
        <Field label={t("permit.issueDate")}>
          <Input type="date" {...form.register("permit_issue_date")} />
        </Field>
        <Field label={t("permit.validUntil")}>
          <Input type="date" {...form.register("permit_valid_until")} />
        </Field>
      </div>
      <Field label={t("permit.committee")}>
        <Input {...form.register("permit_committee")} />
      </Field>
      {save.isError && <Alert>{message(save.error)}</Alert>}
      <div className="flex gap-2">
        <Button type="submit" disabled={save.isPending}>
          {t("permit.save")}
        </Button>
        <Button type="button" variant="ghost" onClick={onDone}>
          {t("permit.back")}
        </Button>
      </div>
    </form>
  );
}

/** Who approves what in the project's area, how to reach them, and where each detail came from. */
export function AuthoritiesPanel({ projectId }: { projectId: string }) {
  const { t } = useTranslation();
  const authorities = $api.useQuery("get", "/api/v1/projects/{project_id}/authorities", {
    params: { path: { project_id: projectId } },
  });
  const list = authorities.data ?? [];
  return (
    <section className="space-y-3">
      <div>
        <h2 className="font-display text-xl font-extrabold">🏛️ {t("directory.title")}</h2>
        <p className="text-sm text-ink-soft">{t("directory.hint")}</p>
      </div>
      {authorities.isSuccess && list.length === 0 && <p className="text-sm text-ink-soft">{t("directory.empty")}</p>}
      <div className="grid gap-3 md:grid-cols-2">
        {list.map((a, i) => (
          <AuthorityCard key={a.id} authority={a} index={i} />
        ))}
      </div>
    </section>
  );
}

function AuthorityCard({ authority: a, index }: { authority: AuthorityInfo; index: number }) {
  const { t } = useTranslation();
  return (
    <motion.article
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.05 }}
      whileHover={{ y: -2 }}
      className="space-y-2 rounded-2xl border-2 border-ink bg-surface p-4"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="text-xs text-ink-soft">{t(`authority.${a.type}`)}</div>
          <div className="font-bold">{a.name}</div>
        </div>
        <div className="flex shrink-0 gap-2 text-sm">
          {a.website && (
            <a className="font-bold text-brand underline" href={a.website} target="_blank" rel="noreferrer">
              {t("directory.website")}
            </a>
          )}
          {a.permit_search_url && (
            <a className="font-bold text-brand underline" href={a.permit_search_url} target="_blank" rel="noreferrer">
              {t("directory.permitSearch")}
            </a>
          )}
        </div>
      </div>
      {a.contacts.length === 0 ? (
        <p className="text-xs text-ink-soft">{t("directory.noContacts")}</p>
      ) : (
        <ul className="space-y-1.5">
          {a.contacts.map((c) => (
            <li key={c.id} className="rounded-lg bg-bg px-3 py-2 text-sm">
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="font-medium">{c.purpose}</span>
                <Badge>{t(`directory.channel.${c.channel}`)}</Badge>
                <Badge tone={c.source === "official_site" ? "success" : "neutral"}>{t(`directory.source.${c.source}`)}</Badge>
              </div>
              <div className="mt-1 flex flex-wrap gap-x-3 text-ink-soft" dir="ltr">
                {c.email && <a href={`mailto:${c.email}`}>{c.email}</a>}
                {c.phone && <a href={`tel:${c.phone}`}>{c.phone}</a>}
                {c.url && (
                  <a href={c.url} target="_blank" rel="noreferrer" className="underline">
                    {new URL(c.url).hostname}
                  </a>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </motion.article>
  );
}
