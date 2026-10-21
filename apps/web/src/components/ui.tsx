import type { Tone } from "@arba/shared";
import type { ButtonHTMLAttributes, ComponentProps, ReactNode } from "react";

function cx(...classes: (string | false | null | undefined)[]) {
  return classes.filter(Boolean).join(" ");
}

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";

const BUTTON_VARIANTS: Record<ButtonVariant, string> = {
  primary:
    "bg-ink text-white shadow-[3px_3px_0_0_var(--color-accent)] hover:-translate-y-0.5 hover:shadow-[4px_5px_0_0_var(--color-accent)] active:translate-y-0 active:shadow-[1px_1px_0_0_var(--color-accent)] disabled:bg-ink/50 disabled:shadow-none disabled:translate-y-0",
  secondary:
    "bg-surface text-ink border-2 border-ink hover:-translate-y-0.5 hover:shadow-[3px_3px_0_0_var(--color-ink)] active:translate-y-0 active:shadow-none",
  ghost: "text-brand hover:bg-brand-soft",
  danger:
    "bg-surface text-danger border-2 border-danger/40 hover:bg-danger-soft hover:-translate-y-0.5",
};

export function Button({
  variant = "primary",
  size = "md",
  className,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: ButtonVariant; size?: "sm" | "md" }) {
  return (
    <button
      className={cx(
        "inline-flex items-center justify-center gap-2 rounded-full font-medium transition-all duration-150",
        "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent",
        "disabled:cursor-not-allowed",
        size === "md" ? "min-h-12 px-6 text-base" : "min-h-9 px-4 text-sm",
        BUTTON_VARIANTS[variant],
        className,
      )}
      {...props}
    />
  );
}

export function Input({ className, ...props }: ComponentProps<"input">) {
  return (
    <input
      className={cx(
        "min-h-12 w-full rounded-xl border-2 border-line bg-surface px-3.5 text-base transition-colors",
        "focus:border-ink focus:outline-none focus:shadow-[3px_3px_0_0_var(--color-accent)]",
        "aria-invalid:border-danger",
        className,
      )}
      {...props}
    />
  );
}

export function Field({
  label,
  hint,
  error,
  children,
}: {
  label: string;
  hint?: string;
  error?: string;
  children: ReactNode;
}) {
  return (
    <label className="block space-y-1.5">
      <span className="block text-sm font-medium">{label}</span>
      {children}
      {error ? (
        <span className="block text-sm text-danger">{error}</span>
      ) : hint ? (
        <span className="block text-sm text-ink-soft">{hint}</span>
      ) : null}
    </label>
  );
}

export function Card({ className, ...props }: ComponentProps<"div">) {
  return (
    <div
      className={cx("rounded-2xl border border-line bg-surface p-4 shadow-card", className)}
      {...props}
    />
  );
}

/** Bold card with an ink border and a hard offset shadow, for hero and story content. */
export function BrutalCard({ className, ...props }: ComponentProps<"div">) {
  return (
    <div
      className={cx(
        "rounded-2xl border-2 border-ink bg-surface p-6 shadow-[6px_6px_0_0_var(--color-ink)]",
        className,
      )}
      {...props}
    />
  );
}

const BADGE_TONES: Record<Tone, string> = {
  neutral: "bg-bg text-ink-soft",
  info: "bg-info-soft text-info",
  warning: "bg-warning-soft text-warning",
  success: "bg-success-soft text-success",
  danger: "bg-danger-soft text-danger",
  muted: "bg-muted-soft text-muted",
};

export function Badge({ tone = "neutral", children }: { tone?: Tone; children: ReactNode }) {
  return (
    <span
      className={cx(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium",
        BADGE_TONES[tone],
      )}
    >
      {children}
    </span>
  );
}

export function Alert({ tone = "danger", children }: { tone?: Tone; children: ReactNode }) {
  return (
    <div role="alert" className={cx("rounded-xl px-3 py-2 text-sm", BADGE_TONES[tone])}>
      {children}
    </div>
  );
}

export function Spinner({ label }: { label: string }) {
  return (
    <div className="flex items-center justify-center gap-3 py-12 text-ink-soft" role="status">
      <span className="size-5 animate-spin rounded-full border-2 border-line border-t-accent" />
      {label}
    </div>
  );
}

export function ProgressBar({ done, total }: { done: number; total: number }) {
  const percent = total ? Math.round((done / total) * 100) : 0;
  return (
    <div
      className="h-2.5 w-full overflow-hidden rounded-full bg-line"
      role="progressbar"
      aria-valuenow={percent}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <div
        className="h-full rounded-full bg-gradient-to-l from-accent to-accent-strong transition-[width] duration-700 ease-out"
        style={{ width: `${percent}%` }}
      />
    </div>
  );
}

export { cx };
