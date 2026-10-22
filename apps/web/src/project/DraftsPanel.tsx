import type { Draft } from "@arba/api-client";
import { AnimatePresence, motion } from "motion/react";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useCelebrate } from "../components/Celebrations";
import { Alert, Badge, Button, Input, cx } from "../components/ui";
import { $api, invalidateProjects } from "../lib/api";
import { useErrorMessage } from "../lib/useErrorMessage";

const SOURCES = ["thread", "official_site", "learned", "user"] as const;
const isSource = (value: string | null): value is (typeof SOURCES)[number] =>
  (SOURCES as readonly (string | null)[]).includes(value);

/** Requests and reminders Arba wrote to the approving bodies, waiting for one tap. */
export function DraftsPanel({ projectId, canEdit }: { projectId: string; canEdit: boolean }) {
  const { t } = useTranslation();
  const drafts = $api.useQuery("get", "/api/v1/projects/{project_id}/drafts", {
    params: { path: { project_id: projectId } },
  });
  const list = drafts.data ?? [];
  return (
    <section id="drafts" className="scroll-mt-24">
      <AnimatePresence>
        {list.length > 0 && (
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, height: 0 }}
            className="space-y-3"
          >
            <div>
              <h2 className="flex items-center gap-2 font-display text-xl font-extrabold">
                <motion.span
                  animate={{ x: [0, 4, 0], rotate: [0, -8, 0] }}
                  transition={{ duration: 2.2, repeat: Infinity }}
                >
                  ✉️
                </motion.span>
                {t("drafts.title")}
                <span className="grid min-w-6 place-items-center rounded-full bg-ink px-1.5 text-sm text-white">
                  {list.length}
                </span>
              </h2>
              <p className="text-sm text-ink-soft">{t("drafts.hint")}</p>
            </div>
            <AnimatePresence initial={false}>
              {list.map((d) => (
                <DraftCard key={d.id} projectId={projectId} draft={d} canEdit={canEdit} />
              ))}
            </AnimatePresence>
          </motion.div>
        )}
      </AnimatePresence>
    </section>
  );
}

function DraftCard({ projectId, draft: d, canEdit }: { projectId: string; draft: Draft; canEdit: boolean }) {
  const { t } = useTranslation();
  const message = useErrorMessage();
  const { toast } = useCelebrate();
  const [subject, setSubject] = useState(d.subject);
  const [body, setBody] = useState(d.body);
  const [toEmail, setToEmail] = useState(d.to_email ?? "");
  const [flying, setFlying] = useState(false);
  const textarea = useRef<HTMLTextAreaElement>(null);
  const params = { params: { path: { project_id: projectId, draft_id: d.id } } };
  const after = { onSuccess: () => void invalidateProjects() };
  const save = $api.useMutation("patch", "/api/v1/projects/{project_id}/drafts/{draft_id}");
  const send = $api.useMutation("post", "/api/v1/projects/{project_id}/drafts/{draft_id}/send");
  const submitted = $api.useMutation("post", "/api/v1/projects/{project_id}/drafts/{draft_id}/submitted", after);
  const discard = $api.useMutation("post", "/api/v1/projects/{project_id}/drafts/{draft_id}/discard", after);
  const busy = save.isPending || send.isPending || submitted.isPending || discard.isPending;
  const error = save.error ?? send.error ?? submitted.error ?? discard.error;
  const email = d.channel === "email";
  const to = d.to_name ?? d.to_email ?? "";

  // Grow the text box with its content.
  useEffect(() => {
    const el = textarea.current;
    if (el) {
      el.style.height = "auto";
      el.style.height = `${el.scrollHeight + 4}px`;
    }
  }, [body]);

  const edited = subject !== d.subject || body !== d.body || toEmail !== (d.to_email ?? "");
  const persist = async () => {
    if (!edited) return;
    await save.mutateAsync({
      ...params,
      body: {
        subject,
        body,
        ...(toEmail !== (d.to_email ?? "") ? { to_email: toEmail || null } : {}),
      },
    });
  };

  const sendNow = async () => {
    try {
      await persist();
      await send.mutateAsync(params);
    } catch {
      return;
    }
    setFlying(true);
    toast(t("drafts.sent", { to: d.to_name ?? toEmail }), "📨");
    window.setTimeout(() => void invalidateProjects(), 900);
  };

  return (
    <motion.article
      layout
      initial={{ opacity: 0, y: 16 }}
      animate={flying ? { opacity: 0, x: -260, y: -60, rotate: -8, scale: 0.7 } : { opacity: 1, x: 0, y: 0 }}
      exit={{ opacity: 0, height: 0, marginTop: 0 }}
      transition={flying ? { duration: 0.8, ease: "easeIn" } : undefined}
      className="space-y-3 rounded-2xl border-2 border-ink bg-surface p-4 shadow-[4px_4px_0_0_var(--color-accent)]"
    >
      <div className="flex flex-wrap items-center gap-1.5">
        <Badge tone={d.kind === "reminder" ? "warning" : "info"}>
          {d.kind === "reminder" ? "⏰" : "✉️"} {t(`drafts.${d.kind}`)}
        </Badge>
        <span className="font-bold">{d.requirement_title}</span>
      </div>

      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="font-medium">{t("drafts.to")}:</span>
        {to && <span className="font-bold">{d.to_name}</span>}
        {email && d.to_email && (
          <span dir="ltr" className="text-ink-soft">
            {d.to_email}
          </span>
        )}
        {isSource(d.recipient_source) && <Badge tone="success">{t(`drafts.source.${d.recipient_source}`)}</Badge>}
      </div>
      {email && !d.to_email && (
        <div className="space-y-1.5">
          <p className="text-sm text-ink-soft">{t("drafts.noAddress")}</p>
          <Input
            dir="ltr"
            type="email"
            value={toEmail}
            placeholder={t("drafts.addressPlaceholder")}
            onChange={(e) => setToEmail(e.target.value)}
          />
        </div>
      )}
      {!email && <p className="rounded-lg bg-accent-soft px-3 py-2 text-sm">{t("drafts.portalHint")}</p>}

      <label className="block space-y-1">
        <span className="text-xs font-bold text-ink-soft">{t("drafts.subject")}</span>
        <Input value={subject} disabled={!canEdit} onChange={(e) => setSubject(e.target.value)} />
      </label>
      <textarea
        ref={textarea}
        value={body}
        disabled={!canEdit}
        onChange={(e) => setBody(e.target.value)}
        className="block w-full resize-none rounded-xl border-2 border-line bg-bg p-3 leading-relaxed outline-none focus:border-ink"
      />

      {d.attachments.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5 text-sm">
          <span className="font-medium">📎 {t("drafts.attachments")}:</span>
          {d.attachments.map((a) => (
            <span key={a.id} className="rounded-full bg-bg px-2 py-0.5">
              {a.file_name}
            </span>
          ))}
        </div>
      )}
      {d.missing_documents.length > 0 && (
        <div className="rounded-lg bg-warning-soft px-3 py-2 text-sm">
          <span className="font-medium">⚠️ {t("drafts.missing")}</span> {d.missing_documents.join(" · ")}
        </div>
      )}
      {error && <Alert>{message(error)}</Alert>}

      {canEdit && (
        <div className="flex flex-wrap gap-2">
          {email ? (
            <Button disabled={busy || (!d.to_email && !toEmail)} onClick={() => void sendNow()}>
              📨 {send.isPending ? t("drafts.sending") : t("drafts.send")}
            </Button>
          ) : (
            <>
              <Button
                variant="secondary"
                onClick={() => {
                  void navigator.clipboard?.writeText(`${subject}\n\n${body}`);
                  toast(t("drafts.copied"), "📋");
                }}
              >
                📋 {t("drafts.copy")}
              </Button>
              {d.portal_url && (
                <Button variant="secondary" onClick={() => window.open(d.portal_url!, "_blank", "noopener")}>
                  🔗 {t("drafts.openSite")}
                </Button>
              )}
              <Button
                disabled={busy}
                onClick={() =>
                  void persist().then(() =>
                    submitted.mutate(params, { onSuccess: () => toast(t("drafts.submittedToast"), "✅") }),
                  )
                }
              >
                {t("drafts.submitted")}
              </Button>
            </>
          )}
          <Button variant="ghost" disabled={busy} className={cx("ms-auto")} onClick={() => discard.mutate(params)}>
            {t("drafts.discard")}
          </Button>
        </div>
      )}
    </motion.article>
  );
}
