import type { NotificationItem } from "@arba/api-client";
import { AnimatePresence, motion, useAnimationControls } from "motion/react";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router";
import { $api, api, queryClient } from "../lib/api";
import { cx } from "./ui";

const KIND_ICON: Record<NotificationItem["kind"], string> = {
  approval_needed: "✨",
  authority_request: "📝",
  daily_digest: "☀️",
  whatsapp_connected: "💬",
  import_finished: "🗂️",
  draft_ready: "✉️",
  document_received: "📥",
  document_problem: "⛔",
  test: "🧪",
};

const relative = new Intl.RelativeTimeFormat("he", { numeric: "auto" });

function ago(iso: string) {
  const minutes = Math.round((new Date(iso).getTime() - Date.now()) / 60_000);
  if (Math.abs(minutes) < 1) return null;
  if (Math.abs(minutes) < 60) return relative.format(minutes, "minute");
  const hours = Math.round(minutes / 60);
  if (Math.abs(hours) < 24) return relative.format(hours, "hour");
  return relative.format(Math.round(hours / 24), "day");
}

export function NotificationBell() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const panel = useRef<HTMLDivElement>(null);
  const bell = useAnimationControls();
  const { data } = $api.useQuery("get", "/api/v1/me/notifications", {}, { refetchInterval: 20_000 });
  const unread = data?.unread ?? 0;

  // Ring when the count goes up.
  const previous = useRef(unread);
  useEffect(() => {
    if (unread > previous.current) {
      void bell.start({ rotate: [0, -18, 16, -12, 8, 0], transition: { duration: 0.8 } });
    }
    previous.current = unread;
  }, [unread, bell]);

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !panel.current?.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
    };
  }, [open]);

  const refresh = () =>
    queryClient.invalidateQueries({ predicate: (q) => String(q.queryKey[1]).startsWith("/api/v1/me") });

  const openItem = async (item: NotificationItem) => {
    setOpen(false);
    if (!item.read_at) {
      await api.fetchClient.POST("/api/v1/me/notifications/{notification_id}/read", {
        params: { path: { notification_id: item.id } },
      });
      void refresh();
    }
    if (item.action_path) void navigate(item.action_path);
  };

  const markAll = async () => {
    await api.fetchClient.POST("/api/v1/me/notifications/read-all");
    void refresh();
  };

  return (
    <div className="relative" ref={panel}>
      <button
        aria-label={t("notifications.title")}
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="relative grid size-10 place-items-center rounded-full border-2 border-ink bg-surface transition-transform hover:-translate-y-0.5"
      >
        <motion.span animate={bell} className="text-lg" style={{ originY: 0 }}>
          🔔
        </motion.span>
        <AnimatePresence>
          {unread > 0 && (
            <motion.span
              key={unread}
              initial={{ scale: 0 }}
              animate={{ scale: 1 }}
              exit={{ scale: 0 }}
              transition={{ type: "spring", stiffness: 500, damping: 18 }}
              className="absolute -end-1.5 -top-1.5 grid min-w-5 place-items-center rounded-full border-2 border-ink bg-accent px-1 text-[11px] font-bold text-ink"
            >
              {unread > 9 ? "9+" : unread}
            </motion.span>
          )}
        </AnimatePresence>
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -8, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -8, scale: 0.97 }}
            transition={{ duration: 0.18 }}
            className="absolute end-0 top-12 z-30 w-[min(24rem,calc(100vw-2rem))] overflow-hidden rounded-2xl border-2 border-ink bg-surface shadow-[5px_5px_0_0_var(--color-ink)]"
          >
            <div className="flex items-center justify-between border-b-2 border-line px-4 py-3">
              <span className="font-display font-extrabold">{t("notifications.title")}</span>
              {unread > 0 && (
                <button className="text-xs font-bold text-accent-strong" onClick={() => void markAll()}>
                  {t("notifications.markAll")}
                </button>
              )}
            </div>
            <ul className="max-h-[60vh] overflow-y-auto">
              {(data?.items ?? []).length === 0 && (
                <li className="p-6 text-center text-sm text-ink-soft">{t("notifications.empty")}</li>
              )}
              {(data?.items ?? []).map((item, i) => (
                <motion.li
                  key={item.id}
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: i * 0.03 }}
                >
                  <button
                    onClick={() => void openItem(item)}
                    className={cx(
                      "flex w-full gap-3 border-b border-line px-4 py-3 text-start transition-colors hover:bg-bg",
                      !item.read_at && "bg-accent-soft/40",
                    )}
                  >
                    <span className="text-xl">{KIND_ICON[item.kind]}</span>
                    <span className="min-w-0 flex-1 space-y-0.5">
                      <span className={cx("block text-sm", !item.read_at && "font-bold")}>{item.title}</span>
                      <span className="line-clamp-2 block text-xs text-ink-soft">{item.body}</span>
                      <span className="flex flex-wrap gap-2 pt-0.5 text-[11px] text-ink-soft">
                        <span>{ago(item.created_at) ?? t("notifications.justNow")}</span>
                        {item.deliveries.map((d) => (
                          <DeliveryMark key={d.channel} channel={d.channel} status={d.status} />
                        ))}
                      </span>
                    </span>
                    {!item.read_at && <span className="mt-1.5 size-2 shrink-0 rounded-full bg-accent" />}
                  </button>
                </motion.li>
              ))}
            </ul>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function DeliveryMark({ channel, status }: NotificationItem["deliveries"][number]) {
  const { t } = useTranslation();
  if (status === "skipped" || status === "failed") return null;
  const label = channel === "whatsapp" ? t("notifications.sentWhatsapp") : t("notifications.sentEmail");
  if (status === "queued") return <span title={t("notifications.queued")}>🕓</span>;
  // WhatsApp-style ticks: ✓ sent, ✓✓ delivered, blue ✓✓ read.
  const ticks = status === "sent" ? "✓" : "✓✓";
  return (
    <span title={label} className={cx("font-bold", status === "read" ? "text-info" : "text-ink-soft")}>
      {channel === "whatsapp" ? "💬" : "✉️"} {ticks}
    </span>
  );
}
