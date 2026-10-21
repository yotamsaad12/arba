import { motion, useMotionValueEvent, useScroll } from "motion/react";
import { useMemo, useRef, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { Logo } from "../components/Logo";
import { BrutalCard, cx } from "../components/ui";
import { STAGES, STAGE_ICON, demoModel } from "../scene/model";
import { useFocusLabel } from "../scene/useFocusLabel";
import { LiveWorld } from "../world/LiveWorld";
import type { CameraKey } from "../world/World";
import { useAuthorities } from "../world/authorities";

// Camera path through the story, one key per section.
const CAMERA: CameraKey[] = [
  { at: 0, position: [14, 17, 34], target: [0, 2, 0] },
  { at: 0.2, position: [-13, 6, 17], target: [0, 1.5, 2] },
  { at: 0.4, position: [16, 9, 15], target: [0, 4, 0] },
  { at: 0.6, position: [4, 30, 38], target: [0, 4, -4] },
  { at: 0.8, position: [-17, 8, 15], target: [0, 4, 0] },
  { at: 1, position: [10, 9, 25], target: [0, 4.5, 0] },
];

export function LandingPage() {
  const { t } = useTranslation();
  const authorities = useAuthorities();
  const progress = useRef(0);
  const [build, setBuild] = useState(0);
  const { scrollYProgress } = useScroll();

  useMotionValueEvent(scrollYProgress, "change", (v) => {
    progress.current = v;
    // The house finishes slightly before the last section, so the ending lingers.
    const next = Math.round(Math.min(1, v * 1.12) * 100) / 100;
    setBuild((prev) => (prev === next ? prev : next));
  });

  const model = useMemo(() => demoModel(build, 2), [build]);
  const focus = useFocusLabel(model);
  const focusLabel = model.complete ? undefined : focus;

  return (
    <div className="relative">
      <LiveWorld
        className="fixed inset-0"
        camera="story"
        progress={progress}
        keys={CAMERA}
        model={model}
        authorities={authorities}
        focusLabel={focusLabel}
        chipClassName="hidden sm:flex"
        completeLabel={t("scene.complete")}
        label={t("scene.label")}
      />
      {/* Paper wash on the reading side so text stays legible over the scene. */}
      <div className="pointer-events-none fixed inset-y-0 start-0 hidden w-[55%] bg-gradient-to-l from-bg via-bg/70 to-transparent lg:block" />
      <div className="pointer-events-none fixed inset-x-0 bottom-0 h-[55%] bg-gradient-to-t from-bg via-bg/80 to-transparent lg:hidden" />

      <LandingNav />

      <main className="pointer-events-none relative">
        <Section align="hero">
          <motion.div
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, ease: [0.22, 1, 0.36, 1] }}
            className="pointer-events-auto max-w-xl space-y-6"
          >
            <span className="inline-block rounded-full border-2 border-ink bg-accent-soft px-3 py-1 font-display text-sm font-bold">
              {t("landing.heroKicker")}
            </span>
            <h1 className="font-display text-5xl font-extrabold leading-[1.02] tracking-tight sm:text-6xl lg:text-7xl">
              {t("landing.heroTitle")}
              <br />
              <span className="text-accent-strong">{t("landing.heroAccent")}</span>
            </h1>
            <p className="text-lg leading-relaxed text-ink-soft sm:text-xl">{t("landing.heroBody")}</p>
            <p className="text-sm font-medium text-ink-soft">{t("landing.authorities")}</p>
            <div className="flex flex-wrap gap-3">
              <CtaLink to="/register">{t("landing.start")} ←</CtaLink>
              <CtaLink to="/login" variant="secondary">
                {t("landing.login")}
              </CtaLink>
            </div>
            <motion.p
              className="flex items-center gap-2 text-sm text-ink-soft"
              animate={{ y: [0, 6, 0] }}
              transition={{ duration: 1.8, repeat: Infinity }}
            >
              ↓ {t("landing.scrollHint")}
            </motion.p>
          </motion.div>
        </Section>

        <StorySection title={t("landing.depsTitle")} accent={t("landing.depsAccent")} body={t("landing.depsBody")}>
          <DependencyChain />
        </StorySection>

        <StorySection title={t("landing.nextTitle")} accent={t("landing.nextAccent")} body={t("landing.nextBody")}>
          <NextStepsMock />
        </StorySection>

        <StorySection title={t("landing.mailTitle")} accent={t("landing.mailAccent")} body={t("landing.mailBody")}>
          <MailMock />
        </StorySection>

        <StorySection title={t("landing.floorsTitle")} accent={t("landing.floorsAccent")} body={t("landing.floorsBody")}>
          <StageMeter model={model} />
        </StorySection>

        <StorySection title={t("landing.doneTitle")} accent={t("landing.doneAccent")} body={t("landing.doneBody")}>
          <div className="flex flex-wrap gap-3">
            <CtaLink to="/register">{t("landing.start")} ←</CtaLink>
            <CtaLink to="/login" variant="secondary">
              {t("landing.login")}
            </CtaLink>
          </div>
        </StorySection>
      </main>
    </div>
  );
}

function LandingNav() {
  const { t } = useTranslation();
  return (
    <header className="fixed inset-x-0 top-0 z-30">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-4">
        <Link to="/" aria-label="Arba">
          <Logo />
        </Link>
        <nav className="flex items-center gap-2">
          <Link to="/login" className="hidden rounded-full px-4 py-2 font-medium hover:bg-surface/70 sm:inline-block">
            {t("landing.login")}
          </Link>
          <Link
            to="/register"
            className="rounded-full bg-ink px-5 py-2.5 font-medium text-white shadow-[3px_3px_0_0_var(--color-accent)] transition-transform hover:-translate-y-0.5"
          >
            {t("landing.start")}
          </Link>
        </nav>
      </div>
    </header>
  );
}

function Section({ children, align }: { children: ReactNode; align?: "hero" }) {
  return (
    <section
      className={cx(
        "flex min-h-[100svh] px-4",
        align === "hero" ? "items-end pb-14 pt-24 lg:items-center lg:pb-0" : "items-end pb-10 lg:items-center lg:pb-0",
      )}
    >
      <div className="mx-auto w-full max-w-6xl">{children}</div>
    </section>
  );
}

function StorySection({
  title,
  accent,
  body,
  children,
}: {
  title: string;
  accent: string;
  body: string;
  children: ReactNode;
}) {
  return (
    <Section>
      <motion.div
        initial={{ opacity: 0, y: 60, rotate: -1.5 }}
        whileInView={{ opacity: 1, y: 0, rotate: 0 }}
        viewport={{ amount: 0.45 }}
        transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
        className="pointer-events-auto max-w-lg"
      >
        <BrutalCard className="space-y-5 p-7 sm:p-9">
          <h2 className="font-display text-4xl font-extrabold leading-[1.05] tracking-tight sm:text-5xl">
            {title}
            <br />
            <span className="text-accent-strong">{accent}</span>
          </h2>
          <p className="text-lg leading-relaxed text-ink-soft">{body}</p>
          {children}
        </BrutalCard>
      </motion.div>
    </Section>
  );
}

function CtaLink({ to, children, variant = "primary" }: { to: string; children: ReactNode; variant?: "primary" | "secondary" }) {
  return (
    <Link
      to={to}
      className={cx(
        "inline-flex min-h-12 items-center rounded-full px-6 font-medium transition-all hover:-translate-y-0.5",
        variant === "primary"
          ? "bg-ink text-white shadow-[3px_3px_0_0_var(--color-accent)] hover:shadow-[4px_5px_0_0_var(--color-accent)]"
          : "border-2 border-ink bg-surface hover:shadow-[3px_3px_0_0_var(--color-ink)]",
      )}
    >
      {children}
    </Link>
  );
}

/** Permit → marking → foundations → frame → Form 4, lighting up in order. */
function DependencyChain() {
  const { t } = useTranslation();
  const steps = [t("stage.pre"), t("stage.foundations"), t("stage.skeleton"), t("stage.envelope"), t("stage.form4")];
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {steps.map((step, k) => (
        <motion.div
          key={step}
          className="flex items-center gap-1.5"
          initial={{ opacity: 0.25, scale: 0.9 }}
          whileInView={{ opacity: 1, scale: 1 }}
          viewport={{ amount: 0.8 }}
          transition={{ delay: 0.25 + k * 0.28, type: "spring", stiffness: 260, damping: 16 }}
        >
          <span className="rounded-full border-2 border-ink bg-accent-soft px-3 py-1 text-sm font-bold">{step}</span>
          {k < steps.length - 1 && <span className="text-ink-soft">←</span>}
        </motion.div>
      ))}
    </div>
  );
}

function NextStepsMock() {
  const { t } = useTranslation();
  const rows = [
    { title: t("landing.mockReady"), item: "בדיקת ברזל לפני יציקה", tone: "bg-info-soft text-info" },
    { title: t("landing.mockWaiting"), item: "אישור ממ\"ד מפיקוד העורף", tone: "bg-warning-soft text-warning" },
    { title: t("landing.mockBlocked"), item: "סגירת קירות", tone: "bg-muted-soft text-muted" },
  ];
  return (
    <div className="space-y-2">
      {rows.map((r, k) => (
        <motion.div
          key={r.item}
          className="flex items-center justify-between gap-3 rounded-xl border-2 border-ink/10 bg-bg px-3 py-2.5"
          initial={{ opacity: 0, x: -30 }}
          whileInView={{ opacity: 1, x: 0 }}
          viewport={{ amount: 0.8 }}
          transition={{ delay: 0.2 + k * 0.15, ease: [0.22, 1, 0.36, 1], duration: 0.6 }}
        >
          <span className="font-medium">{r.item}</span>
          <span className={cx("shrink-0 rounded-full px-2.5 py-0.5 text-xs font-bold", r.tone)}>{r.title}</span>
        </motion.div>
      ))}
    </div>
  );
}

function MailMock() {
  const { t } = useTranslation();
  return (
    <motion.div
      className="space-y-3 rounded-xl border-2 border-ink bg-bg p-4"
      initial={{ opacity: 0, y: 20 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ amount: 0.8 }}
      transition={{ delay: 0.2, duration: 0.6 }}
    >
      <div className="flex items-center gap-2 text-sm">
        <span className="grid size-8 place-items-center rounded-full bg-info-soft">✉️</span>
        <div>
          <div className="font-bold">{t("landing.mockMail")}</div>
          <div className="text-ink-soft">{t("landing.mockMailFrom")} · PDF</div>
        </div>
      </div>
      <motion.div
        className="flex items-center justify-between gap-3 rounded-lg bg-accent-soft px-3 py-2 text-sm"
        initial={{ opacity: 0, scale: 0.95 }}
        whileInView={{ opacity: 1, scale: 1 }}
        viewport={{ amount: 0.8 }}
        transition={{ delay: 0.8, type: "spring", stiffness: 200 }}
      >
        <span>✨ {t("landing.mockSuggest")}</span>
        <motion.span
          className="rounded-full bg-ink px-3 py-1 font-bold text-white"
          animate={{ scale: [1, 1.07, 1] }}
          transition={{ duration: 1.4, repeat: Infinity, delay: 1.4 }}
        >
          {t("landing.mockApprove")} ✓
        </motion.span>
      </motion.div>
    </motion.div>
  );
}

function StageMeter({ model }: { model: ReturnType<typeof demoModel> }) {
  const { t } = useTranslation();
  return (
    <div className="grid grid-cols-3 gap-2">
      {STAGES.map((key) => {
        const value = model.stage[key];
        return (
          <div key={key} className="relative overflow-hidden rounded-xl border-2 border-ink/10 bg-bg px-2 py-2 text-center">
            <motion.div
              className="absolute inset-x-0 bottom-0 bg-accent/25"
              initial={false}
              animate={{ height: `${value * 100}%` }}
              transition={{ duration: 0.5 }}
            />
            <div className="relative text-xl">{value >= 1 ? "✅" : STAGE_ICON[key]}</div>
            <div className="relative text-xs font-bold">{t(`stage.${key}`)}</div>
          </div>
        );
      })}
    </div>
  );
}
