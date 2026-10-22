import type { UserSettings } from "@arba/api-client";
import { AnimatePresence, motion } from "motion/react";
import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { useCelebrate } from "../components/Celebrations";
import { Alert, BrutalCard, Button, Card, Field, Input, Spinner, cx } from "../components/ui";
import { $api, queryClient } from "../lib/api";
import { useErrorMessage } from "../lib/useErrorMessage";

const refreshMe = () =>
  queryClient.invalidateQueries({ predicate: (q) => String(q.queryKey[1]).startsWith("/api/v1/me") });

export function SettingsPage() {
  const { t } = useTranslation();
  const message = useErrorMessage();
  const { data: s, error } = $api.useQuery("get", "/api/v1/me/settings");

  if (error) return <Alert>{message(error)}</Alert>;
  if (!s) return <Spinner label={t("app.loading")} />;

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div>
        <h1 className="font-display text-3xl font-extrabold sm:text-4xl">{t("settings.title")}</h1>
        <p className="text-ink-soft">{t("settings.subtitle")}</p>
      </div>
      {s.whatsapp_available && <WhatsAppCard settings={s} />}
      <Preferences settings={s} />
      <TestCard />
    </div>
  );
}

function WhatsAppCard({ settings: s }: { settings: UserSettings }) {
  const { t } = useTranslation();
  const message = useErrorMessage();
  const celebrate = useCelebrate();
  const [phone, setPhone] = useState("");
  const [consent, setConsent] = useState(false);
  const [code, setCode] = useState("");
  const [sentTo, setSentTo] = useState<string | null>(null);

  const start = $api.useMutation("post", "/api/v1/me/whatsapp/start", {
    onSuccess: (data) => setSentTo(data.phone),
  });
  const confirm = $api.useMutation("post", "/api/v1/me/whatsapp/confirm", {
    onSuccess: () => {
      celebrate.burst(window.innerWidth / 2, 220);
      celebrate.toast(t("settings.connectedToast"), "💬");
      setSentTo(null);
      void refreshMe();
    },
  });
  const disconnect = $api.useMutation("delete", "/api/v1/me/whatsapp", { onSuccess: () => void refreshMe() });
  const error = start.error ?? confirm.error ?? disconnect.error;

  return (
    <BrutalCard className="relative space-y-4 overflow-hidden">
      <span aria-hidden className="absolute -end-6 -top-6 text-8xl opacity-10">
        💬
      </span>
      <div className="flex items-center gap-3">
        <span className="grid size-12 place-items-center rounded-2xl border-2 border-ink bg-[#25d366] text-2xl">💬</span>
        <div>
          <h2 className="font-display text-2xl font-extrabold">{t("settings.whatsappTitle")}</h2>
          <p className="text-sm text-ink-soft">{t("settings.whatsappPitch")}</p>
        </div>
      </div>

      <AnimatePresence mode="wait">
        {s.whatsapp.connected ? (
          <motion.div
            key="connected"
            initial={{ opacity: 0, scale: 0.97 }}
            animate={{ opacity: 1, scale: 1 }}
            className="space-y-2"
          >
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-success-soft px-4 py-3">
              <span className="font-bold text-success">
                ✅ {t("settings.connected")} <span dir="ltr">{s.whatsapp.phone}</span>
              </span>
              <Button variant="secondary" size="sm" disabled={disconnect.isPending} onClick={() => disconnect.mutate({})}>
                {t("settings.disconnect")}
              </Button>
            </div>
            {s.whatsapp.opted_out && <Alert tone="warning">{t("settings.optedOut")}</Alert>}
          </motion.div>
        ) : sentTo ? (
          <motion.form
            key="code"
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            className="space-y-3"
            onSubmit={(e) => {
              e.preventDefault();
              confirm.mutate({ body: { code } });
            }}
          >
            <p className="text-sm">{t("settings.codeSent", { phone: sentTo })}</p>
            <div className="flex gap-2">
              <Input
                autoFocus
                inputMode="numeric"
                autoComplete="one-time-code"
                dir="ltr"
                maxLength={6}
                value={code}
                onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
                className="max-w-40 text-center font-display text-2xl tracking-[0.4em]"
                aria-label={t("settings.code")}
              />
              <Button type="submit" disabled={code.length < 6 || confirm.isPending}>
                {t("settings.confirm")}
              </Button>
            </div>
          </motion.form>
        ) : (
          <motion.form
            key="phone"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="space-y-3"
            onSubmit={(e) => {
              e.preventDefault();
              start.mutate({ body: { phone, consent: true } });
            }}
          >
            <Field label={t("settings.phone")}>
              <Input
                type="tel"
                dir="ltr"
                autoComplete="tel"
                placeholder="050-123-4567"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
              />
            </Field>
            <label className="flex cursor-pointer items-start gap-2 text-sm">
              <input
                type="checkbox"
                className="mt-0.5 size-4 accent-ink"
                checked={consent}
                onChange={(e) => setConsent(e.target.checked)}
              />
              {t("settings.consent")}
            </label>
            <Button type="submit" disabled={!consent || phone.length < 9 || start.isPending}>
              💬 {t("settings.sendCode")}
            </Button>
          </motion.form>
        )}
      </AnimatePresence>
      {error && <Alert>{message(error)}</Alert>}
      {s.whatsapp_simulator && (
        <Link to="/dev/whatsapp" className="inline-block text-sm font-bold text-accent-strong underline underline-offset-4">
          📱 {t("settings.simulator")}
        </Link>
      )}
    </BrutalCard>
  );
}

function Preferences({ settings: s }: { settings: UserSettings }) {
  const { t } = useTranslation();
  const message = useErrorMessage();
  const [saved, setSaved] = useState(false);
  const update = $api.useMutation("patch", "/api/v1/me/settings", {
    onSuccess: () => {
      setSaved(true);
      window.setTimeout(() => setSaved(false), 1500);
      void refreshMe();
    },
  });
  const set = (body: Partial<UserSettings>) => update.mutate({ body });

  return (
    <Card className="space-y-6 p-5">
      <Section title={t("settings.channelsTitle")}>
        <Toggle
          label={`💬 ${t("settings.viaWhatsapp")}`}
          checked={s.notify_whatsapp}
          disabled={!s.whatsapp.connected}
          onChange={(v) => set({ notify_whatsapp: v })}
        />
        <Toggle label={`✉️ ${t("settings.viaEmail")}`} checked={s.notify_email} onChange={(v) => set({ notify_email: v })} />
      </Section>
      <Section title={t("settings.quietTitle")}>
        <Toggle label={`🌙 ${t("settings.quietNights")}`} checked={s.quiet_nights} onChange={(v) => set({ quiet_nights: v })} />
        <Toggle label={`🕯️ ${t("settings.quietShabbat")}`} checked={s.quiet_shabbat} onChange={(v) => set({ quiet_shabbat: v })} />
      </Section>
      <Section title={t("settings.digestTitle")} hint={t("settings.digestHint")}>
        <label className="flex items-center gap-3 text-sm font-medium">
          ☀️ {t("settings.digestHour")}
          <select
            value={s.digest_hour}
            onChange={(e) => set({ digest_hour: Number(e.target.value) })}
            className="min-h-10 rounded-xl border-2 border-ink bg-surface px-3 font-display font-bold"
          >
            {[5, 6, 7, 8, 9, 10, 11, 12].map((h) => (
              <option key={h} value={h}>
                {String(h).padStart(2, "0")}:00
              </option>
            ))}
          </select>
        </label>
      </Section>
      <div className="h-5 text-sm">
        <AnimatePresence>
          {saved && (
            <motion.span initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className="font-bold text-success">
              ✓ {t("settings.saved")}
            </motion.span>
          )}
        </AnimatePresence>
        {update.error && <span className="text-danger">{message(update.error)}</span>}
      </div>
    </Card>
  );
}

function Section({ title, hint, children }: { title: string; hint?: string; children: ReactNode }) {
  return (
    <section className="space-y-2">
      <div>
        <h3 className="font-display text-lg font-bold">{title}</h3>
        {hint && <p className="text-sm text-ink-soft">{hint}</p>}
      </div>
      <div className="space-y-2">{children}</div>
    </section>
  );
}

function Toggle({
  label,
  checked,
  disabled,
  onChange,
}: {
  label: string;
  checked: boolean;
  disabled?: boolean;
  onChange: (value: boolean) => void;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={cx(
        "flex w-full items-center justify-between gap-3 rounded-xl border-2 px-3 py-2.5 text-start text-sm font-medium transition-colors",
        checked ? "border-ink bg-accent-soft" : "border-line bg-surface",
        disabled && "opacity-50",
      )}
    >
      {label}
      <span className={cx("relative h-6 w-11 shrink-0 rounded-full border-2 border-ink transition-colors", checked ? "bg-accent" : "bg-line")}>
        <motion.span
          className="absolute top-0.5 size-4 rounded-full border-2 border-ink bg-surface"
          initial={false}
          animate={{ insetInlineStart: checked ? "1.375rem" : "0.125rem" }}
          transition={{ type: "spring", stiffness: 500, damping: 30 }}
        />
      </span>
    </button>
  );
}

function TestCard() {
  const { t } = useTranslation();
  const celebrate = useCelebrate();
  const test = $api.useMutation("post", "/api/v1/me/notifications/test", {
    onSuccess: (result) => {
      if (result.some((d) => d.status === "sent")) celebrate.toast(t("settings.testToast"), "🧪");
      void refreshMe();
    },
  });
  const label = {
    sent: `✅ ${t("settings.testSent")}`,
    delivered: `✅ ${t("settings.testSent")}`,
    read: `✅ ${t("settings.testSent")}`,
    skipped: `➖ ${t("settings.testSkipped")}`,
    failed: `❌ ${t("settings.testFailed")}`,
    queued: `🕓 ${t("settings.testQueued")}`,
  } as const;

  return (
    <Card className="space-y-3 p-5">
      <Section title={`🧪 ${t("settings.testTitle")}`} hint={t("settings.testHint")}>
        <Button variant="secondary" disabled={test.isPending} onClick={() => test.mutate({})}>
          {t("settings.testButton")}
        </Button>
      </Section>
      {test.isError && <Alert>{t("errors.unknown_error")}</Alert>}
      <AnimatePresence>
        {test.data && (
          <motion.ul initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="space-y-1.5 text-sm">
            {test.data.map((d) => (
              <li key={d.channel} className="rounded-xl bg-bg px-3 py-2">
                <span className="font-bold">
                  {d.channel === "whatsapp" ? `💬 ${t("settings.viaWhatsapp")}` : `✉️ ${t("settings.viaEmail")}`}
                </span>{" "}
                · {label[d.status]}
                {d.error && (
                  <span dir="ltr" className="mt-1 block break-words font-mono text-xs text-ink-soft">
                    {d.error}
                  </span>
                )}
              </li>
            ))}
          </motion.ul>
        )}
      </AnimatePresence>
    </Card>
  );
}
