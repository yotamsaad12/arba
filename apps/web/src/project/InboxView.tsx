import type { Requirement, Stage, Suggestion, ThreadSummary } from "@arba/api-client";
import { AnimatePresence, motion } from "motion/react";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useSearchParams } from "react-router";
import { useCelebrate } from "../components/Celebrations";
import { Alert, Spinner, cx } from "../components/ui";
import { $api, invalidateProjects } from "../lib/api";
import { fileIcon, formatBytes, formatDateTime } from "../lib/upload";
import { useErrorMessage } from "../lib/useErrorMessage";
import { RequirementPicker } from "./RequirementPicker";
import { SuggestionCard } from "./SuggestionCard";

interface Props {
  projectId: string;
  suggestions: Suggestion[];
  inboxAddress: string;
  canEdit: boolean;
  stages: Stage[];
  requirements: Requirement[];
}

export function InboxView(props: Props) {
  const { projectId, inboxAddress } = props;
  const { t } = useTranslation();
  const message = useErrorMessage();
  const [search, setSearch] = useSearchParams();
  const selected = search.get("thread");
  const threads = $api.useQuery("get", "/api/v1/projects/{project_id}/inbox", {
    params: { path: { project_id: projectId } },
  });

  const select = (id: string | null) =>
    setSearch(id ? { tab: "inbox", thread: id } : { tab: "inbox" }, { replace: !id });

  if (threads.error) return <Alert>{message(threads.error)}</Alert>;
  if (!threads.data) return <Spinner label={t("app.loading")} />;
  if (!threads.data.length) return <EmptyInbox address={inboxAddress} />;

  const unfiled = threads.data.filter((th) => !th.requirement_id).length;

  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-4 md:grid-cols-[minmax(0,22rem)_minmax(0,1fr)]">
      <div className={cx("space-y-2", selected && "hidden md:block")}>
        {unfiled > 0 && (
          <p className="rounded-xl bg-accent-soft px-3 py-2 text-sm font-bold">
            📥 {t("inbox.unfiledCount", { count: unfiled })}
          </p>
        )}
        <ul className="space-y-2">
          {threads.data.map((thread, i) => (
            <ThreadRow
              key={thread.id}
              thread={thread}
              suggested={props.suggestions.some((s) => s.thread_id === thread.id)}
              index={i}
              active={thread.id === selected}
              onSelect={() => select(thread.id)}
            />
          ))}
        </ul>
      </div>
      <div className={cx(!selected && "hidden md:block")}>
        <AnimatePresence mode="wait">
          {selected ? (
            <ThreadPanel key={selected} threadId={selected} onBack={() => select(null)} {...props} />
          ) : (
            <motion.div
              key="empty"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="grid h-full min-h-60 place-items-center rounded-2xl border-2 border-dashed border-line text-ink-soft"
            >
              ✉️ {t("inbox.pickThread")}
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}

const AVATAR_COLORS = ["bg-info-soft", "bg-accent-soft", "bg-success-soft", "bg-danger-soft", "bg-brand-soft"];

function avatarColor(email: string) {
  let hash = 0;
  for (const ch of email) hash = (hash * 31 + ch.charCodeAt(0)) | 0;
  return AVATAR_COLORS[Math.abs(hash) % AVATAR_COLORS.length];
}

function ThreadRow({
  thread: th,
  suggested,
  index,
  active,
  onSelect,
}: {
  thread: ThreadSummary;
  suggested: boolean;
  index: number;
  active: boolean;
  onSelect: () => void;
}) {
  const { t } = useTranslation();
  const name = th.counterparty_name || th.counterparty_email;
  const unread = th.unread_count > 0;
  return (
    <motion.li
      layout
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: Math.min(index, 10) * 0.04 }}
    >
      <button
        onClick={onSelect}
        className={cx(
          "relative flex w-full gap-3 rounded-2xl border-2 p-3 text-start transition-all hover:-translate-y-0.5",
          active ? "border-ink bg-surface shadow-[4px_4px_0_0_var(--color-ink)]" : "border-line bg-surface",
        )}
      >
        <span
          className={cx(
            "grid size-10 shrink-0 place-items-center rounded-full border-2 border-ink font-display font-bold",
            avatarColor(th.counterparty_email),
          )}
        >
          {name.trim().charAt(0).toUpperCase()}
        </span>
        <span className="min-w-0 flex-1 space-y-0.5">
          <span className="flex items-baseline justify-between gap-2">
            <span className={cx("truncate", unread ? "font-bold" : "font-medium")}>{name}</span>
            <span className="shrink-0 text-xs text-ink-soft">{formatDateTime(th.last_message_at)}</span>
          </span>
          <span className={cx("block truncate text-sm", unread && "font-bold")}>{th.subject}</span>
          <span className="block truncate text-xs text-ink-soft">{th.snippet}</span>
          <span className="flex flex-wrap gap-1.5 pt-1 text-xs">
            {suggested ? (
              <span className="rounded-full bg-ink px-2 py-0.5 font-bold text-white">
                ✨ {t("suggestions.approve")}?
              </span>
            ) : th.requirement_title ? (
              <span className="truncate rounded-full bg-success-soft px-2 py-0.5 font-medium text-success">
                🗂️ {th.requirement_title}
              </span>
            ) : (
              <span className="rounded-full bg-accent-soft px-2 py-0.5 font-bold text-warning">
                {t("inbox.unfiled")}
              </span>
            )}
            {th.attachment_count > 0 && (
              <span className="rounded-full bg-bg px-2 py-0.5">📎 {th.attachment_count}</span>
            )}
            {th.message_count > 1 && (
              <span className="rounded-full bg-bg px-2 py-0.5">
                {t("inbox.messages", { count: th.message_count })}
              </span>
            )}
          </span>
        </span>
        {unread && <span className="absolute end-3 top-3 size-2.5 rounded-full bg-accent" />}
      </button>
    </motion.li>
  );
}

function ThreadPanel({
  projectId,
  threadId,
  canEdit,
  stages,
  requirements,
  suggestions,
  onBack,
}: Props & { threadId: string; onBack: () => void }) {
  const suggestion = suggestions.find((s) => s.thread_id === threadId);
  const { t } = useTranslation();
  const message = useErrorMessage();
  const celebrate = useCelebrate();
  const path = { project_id: projectId, thread_id: threadId };
  const thread = $api.useQuery("get", "/api/v1/projects/{project_id}/threads/{thread_id}", {
    params: { path },
  });
  const read = $api.useMutation("post", "/api/v1/projects/{project_id}/threads/{thread_id}/read", {
    onSuccess: () => void invalidateProjects(),
  });
  const file = $api.useMutation("patch", "/api/v1/projects/{project_id}/threads/{thread_id}", {
    onSuccess: (data) => {
      celebrate.toast(data.requirement_id ? t("inbox.filedToast") : t("inbox.unfiledToast"), "🗂️");
      void invalidateProjects();
    },
  });

  // Mark read once per opened thread.
  const unread = thread.data?.unread_count ?? 0;
  const markedFor = useRef<string | null>(null);
  useEffect(() => {
    if (unread > 0 && markedFor.current !== threadId) {
      markedFor.current = threadId;
      read.mutate({ params: { path: { project_id: projectId, thread_id: threadId } } });
    }
  }, [projectId, threadId, unread, read]);

  if (thread.error) return <Alert>{message(thread.error)}</Alert>;
  if (!thread.data) return <Spinner label={t("app.loading")} />;
  const th = thread.data;

  return (
    <motion.div
      initial={{ opacity: 0, x: -20 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0 }}
      className="space-y-4 rounded-2xl border-2 border-ink bg-surface p-4 shadow-[5px_5px_0_0_var(--color-ink)] sm:p-5"
    >
      <button onClick={onBack} className="text-sm font-medium text-ink-soft md:hidden">
        → {t("inbox.back")}
      </button>
      <div className="space-y-1">
        <h2 className="font-display text-xl font-extrabold">{th.subject}</h2>
        <p className="text-sm text-ink-soft">
          {th.counterparty_name} <span dir="ltr">&lt;{th.counterparty_email}&gt;</span>
        </p>
      </div>

      {suggestion ? (
        <SuggestionCard
          projectId={projectId}
          suggestion={suggestion}
          stages={stages}
          requirements={requirements}
          canEdit={canEdit}
          compact
        />
      ) : (
      <div
        className={cx(
          "flex flex-wrap items-center gap-2 rounded-xl p-3",
          th.requirement_id ? "bg-success-soft" : "bg-accent-soft",
        )}
      >
        <span className="text-sm font-bold">🗂️ {t("inbox.fileTo")}:</span>
        {canEdit ? (
          <RequirementPicker
            stages={stages}
            requirements={requirements}
            value={th.requirement_id}
            disabled={file.isPending}
            className="min-w-0 flex-1"
            onChange={(requirement_id) => file.mutate({ params: { path }, body: { requirement_id } })}
          />
        ) : (
          <span className="text-sm">{th.requirement_title ?? t("inbox.unfiled")}</span>
        )}
      </div>
      )}
      {file.error && <Alert>{message(file.error)}</Alert>}

      <ol className="space-y-3">
        {th.messages.map((m, i) => (
          <motion.li
            key={m.id}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.06 }}
            className={cx(
              "space-y-2 rounded-2xl border-2 p-3.5",
              m.direction === "inbound" ? "me-6 border-line bg-bg" : "ms-6 border-brand/20 bg-brand-soft",
            )}
          >
            <div className="flex flex-wrap items-baseline justify-between gap-2 text-sm">
              <span className="font-bold">{m.from_name || m.from_email}</span>
              <span className="text-xs text-ink-soft">{formatDateTime(m.sent_at)}</span>
            </div>
            <p dir="auto" className="whitespace-pre-wrap break-words text-sm leading-relaxed">
              {m.text_body}
            </p>
            {m.attachments.length > 0 && (
              <div className="flex flex-wrap gap-2 pt-1">
                {m.attachments.map((a) => (
                  <a
                    key={a.id}
                    href={a.download_url}
                    className="inline-flex max-w-full items-center gap-2 rounded-xl border-2 border-ink bg-surface px-3 py-1.5 text-sm font-medium transition-transform hover:-translate-y-0.5"
                  >
                    <span>{fileIcon(a.file_name, a.content_type)}</span>
                    <span className="truncate">{a.file_name}</span>
                    <span dir="ltr" className="shrink-0 text-xs text-ink-soft">
                      {formatBytes(a.size_bytes)}
                    </span>
                  </a>
                ))}
              </div>
            )}
          </motion.li>
        ))}
      </ol>
    </motion.div>
  );
}

function EmptyInbox({ address }: { address: string }) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);
  return (
    <div className="flex flex-col items-center gap-4 rounded-3xl border-2 border-dashed border-ink/30 p-10 text-center">
      <motion.span
        className="text-6xl"
        animate={{ y: [0, -10, 0], rotate: [0, -6, 0] }}
        transition={{ duration: 2.4, repeat: Infinity }}
      >
        ✉️
      </motion.span>
      <p className="max-w-md text-ink-soft">{t("inbox.empty")}</p>
      <button
        onClick={() =>
          void navigator.clipboard?.writeText(address).then(() => {
            setCopied(true);
            window.setTimeout(() => setCopied(false), 1600);
          })
        }
        className="rounded-full border-2 border-ink bg-surface px-4 py-2 font-medium shadow-[3px_3px_0_0_var(--color-ink)] transition-transform hover:-translate-y-0.5"
      >
        <span dir="ltr">{address}</span> · {copied ? t("inbox.copied") : t("inbox.copy")}
      </button>
    </div>
  );
}
