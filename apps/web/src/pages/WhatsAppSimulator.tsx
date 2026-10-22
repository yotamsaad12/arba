import type { SimMessage } from "@arba/api-client";
import { AnimatePresence, motion } from "motion/react";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Spinner, cx } from "../components/ui";
import { $api, invalidateProjects, queryClient } from "../lib/api";

const WA = { header: "#075e54", chat: "#efeae2", mine: "#d9fdd3", theirs: "#ffffff", link: "#027eb5" };

/** Dev only: what each person would see on WhatsApp, with working buttons. */
export function WhatsAppSimulatorPage() {
  const { t } = useTranslation();
  const chats = $api.useQuery("get", "/api/v1/dev/whatsapp/chats", {}, { refetchInterval: 3000 });
  const [phone, setPhone] = useState<string | null>(null);
  const active = phone ?? chats.data?.[0]?.phone ?? null;

  return (
    <div className="space-y-5">
      <div>
        <h1 className="font-display text-3xl font-extrabold">📱 {t("simulator.title")}</h1>
        <p className="text-ink-soft">{t("simulator.hint")}</p>
      </div>
      <div className="grid gap-6 md:grid-cols-[16rem_minmax(0,1fr)]">
        <aside className="space-y-2">
          <h2 className="font-display font-bold">{t("simulator.chats")}</h2>
          {chats.data?.length === 0 && <p className="text-sm text-ink-soft">{t("simulator.empty")}</p>}
          {chats.data?.map((c) => (
            <button
              key={c.phone}
              onClick={() => setPhone(c.phone)}
              className={cx(
                "block w-full rounded-xl border-2 p-3 text-start",
                c.phone === active ? "border-ink bg-surface shadow-[3px_3px_0_0_var(--color-ink)]" : "border-line bg-surface",
              )}
            >
              <span className="block font-bold">{c.name ?? c.phone}</span>
              <span dir="ltr" className="block text-xs text-ink-soft">
                {c.phone}
              </span>
              <span className="line-clamp-1 block text-xs text-ink-soft">{c.last_text}</span>
            </button>
          ))}
        </aside>
        {active ? <Phone phone={active} /> : chats.isPending && <Spinner label={t("app.loading")} />}
      </div>
    </div>
  );
}

function Phone({ phone }: { phone: string }) {
  const { t } = useTranslation();
  const messages = $api.useQuery(
    "get",
    "/api/v1/dev/whatsapp/chats/{phone}",
    { params: { path: { phone } } },
    { refetchInterval: 3000 },
  );
  const send = $api.useMutation("post", "/api/v1/dev/whatsapp/chats/{phone}/send", {
    onSuccess: (data) => {
      queryClient.setQueryData(["get", "/api/v1/dev/whatsapp/chats/{phone}", { params: { path: { phone } } }], data);
      // A button press can file things and close notifications: refresh both.
      void invalidateProjects();
      void queryClient.invalidateQueries({
        predicate: (q) => String(q.queryKey[1]).startsWith("/api/v1/me"),
      });
    },
  });
  const [text, setText] = useState("");
  const scroller = useRef<HTMLDivElement>(null);
  const count = messages.data?.length ?? 0;
  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: "smooth" });
  }, [count]);

  const press = (b: { id: string; title: string }) =>
    send.mutate({ params: { path: { phone } }, body: { button_id: b.id, button_title: b.title } });

  return (
    <div className="mx-auto w-full max-w-sm">
      <div className="overflow-hidden rounded-[2.5rem] border-[10px] border-ink bg-ink shadow-[8px_8px_0_0_var(--color-accent)]">
        <div className="flex items-center gap-3 px-4 py-3 text-white" style={{ background: WA.header }}>
          <span className="grid size-9 place-items-center rounded-full bg-accent font-display font-extrabold text-ink">A</span>
          <div className="leading-tight">
            <div className="font-bold">{t("simulator.business")} ✔️</div>
            <div dir="ltr" className="text-xs opacity-80">
              {phone}
            </div>
          </div>
        </div>
        <div ref={scroller} className="h-[30rem] space-y-2 overflow-y-auto p-3" style={{ background: WA.chat }}>
          <AnimatePresence initial={false}>
            {messages.data?.map((m) => (
              <Bubble key={m.id} message={m} onPress={press} disabled={send.isPending} />
            ))}
          </AnimatePresence>
        </div>
        <form
          className="flex gap-2 p-2"
          style={{ background: "#f0f2f5" }}
          onSubmit={(e) => {
            e.preventDefault();
            if (!text.trim()) return;
            send.mutate({ params: { path: { phone } }, body: { text } });
            setText("");
          }}
        >
          <input
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={t("simulator.placeholder")}
            className="min-h-10 flex-1 rounded-full bg-white px-4 text-sm outline-none"
          />
          <button
            className="grid size-10 place-items-center rounded-full text-white"
            style={{ background: WA.header }}
            aria-label={t("simulator.send")}
          >
            ➤
          </button>
        </form>
      </div>
    </div>
  );
}

const LINK = /(https?:\/\/\S+)/g;
const IS_LINK = /^https?:\/\//;

function Bubble({
  message: m,
  onPress,
  disabled,
}: {
  message: SimMessage;
  onPress: (b: { id: string; title: string }) => void;
  disabled: boolean;
}) {
  // Arba's messages arrive on the right in a Hebrew WhatsApp; the person's own on the left.
  const mine = m.direction === "in";
  const time = new Date(m.created_at).toLocaleTimeString("he-IL", { hour: "2-digit", minute: "2-digit" });
  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 12, scale: 0.96 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      className={cx("flex max-w-[85%] flex-col gap-1", mine ? "ms-auto items-end" : "items-start")}
    >
      <div
        className="rounded-xl px-3 py-2 text-sm shadow-sm"
        style={{ background: mine ? WA.mine : WA.theirs, borderStartStartRadius: mine ? undefined : 2 }}
      >
        <p dir="auto" className="whitespace-pre-wrap break-words">
          {m.text.split(LINK).map((part, i) =>
            IS_LINK.test(part) ? (
              <a key={i} href={part} className="underline" style={{ color: WA.link }} dir="ltr">
                {part}
              </a>
            ) : (
              part
            ),
          )}
        </p>
        <div className="mt-0.5 text-end text-[10px] text-gray-500">
          {time} {mine && <span style={{ color: "#53bdeb" }}>✓✓</span>}
        </div>
      </div>
      {m.buttons.length > 0 && (
        <div className="flex w-full flex-col gap-1">
          {m.buttons.map((b) => (
            <motion.button
              key={b.id}
              whileTap={{ scale: 0.97 }}
              disabled={disabled}
              onClick={() => onPress(b as { id: string; title: string })}
              className="w-full rounded-xl bg-white px-3 py-2 text-sm font-medium shadow-sm disabled:opacity-60"
              style={{ color: WA.link }}
            >
              ↩︎ {b.title}
            </motion.button>
          ))}
        </div>
      )}
    </motion.div>
  );
}
