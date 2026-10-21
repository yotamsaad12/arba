import { AnimatePresence, motion } from "motion/react";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Link, useLocation, useOutlet } from "react-router";
import { useAuth } from "../auth/AuthProvider";
import { $api } from "../lib/api";
import { demoModel } from "../scene/model";
import { LiveWorld } from "../world/LiveWorld";
import { useAuthorities } from "../world/authorities";
import { Logo } from "./Logo";
import { Button } from "./ui";

export function AppLayout() {
  const { t } = useTranslation();
  const { signOut } = useAuth();
  const location = useLocation();
  // Captured per render, so the page that is fading out keeps showing its own content.
  const outlet = useOutlet();
  const me = $api.useQuery("get", "/api/v1/auth/me");

  return (
    <div className="min-h-dvh">
      <header className="sticky top-0 z-20 border-b border-line/70 bg-bg/85 backdrop-blur-md">
        <div className="mx-auto flex h-16 max-w-5xl items-center justify-between gap-3 px-4">
          <Link to="/" aria-label="Arba">
            <Logo />
          </Link>
          <div className="flex items-center gap-2 text-sm text-ink-soft">
            {me.data && (
              <span className="hidden items-center gap-2 sm:flex">
                <span className="grid size-8 place-items-center rounded-full border-2 border-ink bg-accent-soft font-display font-bold text-ink">
                  {me.data.name.trim().charAt(0)}
                </span>
                {me.data.name}
              </span>
            )}
            <Button variant="ghost" size="sm" onClick={() => void signOut()}>
              {t("app.logout")}
            </Button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-4 py-6 pb-20">
        <AnimatePresence mode="wait">
          <motion.div
            key={location.pathname}
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
          >
            {outlet}
          </motion.div>
        </AnimatePresence>
      </main>
    </div>
  );
}

/** Sign-in pages float over a live construction site that keeps building itself. */
export function AuthLayout({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  const authorities = useAuthorities();
  const [step, setStep] = useState(0);
  useEffect(() => {
    const id = window.setInterval(() => setStep((s) => (s + 1) % 34), 900);
    return () => window.clearInterval(id);
  }, []);
  // Hold on the finished house for a few beats before starting over.
  const model = useMemo(() => demoModel(Math.min(1, step / 28), 2), [step]);

  return (
    <div className="relative min-h-dvh overflow-hidden">
      <LiveWorld
        className="absolute inset-0"
        camera="orbit"
        model={model}
        authorities={authorities}
        completeLabel={t("scene.complete")}
        label={t("scene.label")}
      />
      <div className="pointer-events-none absolute inset-0 bg-gradient-to-t from-bg/90 via-bg/30 to-transparent lg:bg-gradient-to-l lg:from-bg/95 lg:via-bg/40" />
      <div className="pointer-events-none relative flex min-h-dvh flex-col justify-end px-4 py-8 lg:mx-auto lg:max-w-6xl lg:justify-center">
        <motion.div
          initial={{ opacity: 0, y: 40 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
          className="pointer-events-auto w-full max-w-md space-y-5"
        >
          <Link to="/" className="inline-block" aria-label="Arba">
            <Logo size="lg" />
          </Link>
          <p className="font-display text-xl font-bold">{t("app.tagline")}</p>
          {children}
        </motion.div>
      </div>
    </div>
  );
}
