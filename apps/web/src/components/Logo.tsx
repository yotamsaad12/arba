import { cx } from "./ui";

/** The Arba mark: a gable roof that doubles as the "A". */
export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden="true">
      <rect width="32" height="32" rx="8" fill="var(--color-brand)" />
      <path
        d="M6 23 16 8l10 15"
        fill="none"
        stroke="var(--color-accent)"
        strokeWidth="3.2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path d="M10.5 18h11" stroke="#fff" strokeWidth="2.6" strokeLinecap="round" />
    </svg>
  );
}

/** Brand name is always Latin and left-to-right, even inside the Hebrew UI. */
export function Logo({ size = "md", light }: { size?: "md" | "lg"; light?: boolean }) {
  return (
    <span dir="ltr" className="inline-flex items-center gap-2">
      <LogoMark className={size === "lg" ? "size-12" : "size-8"} />
      <span
        className={cx(
          "font-display font-extrabold tracking-tight",
          size === "lg" ? "text-4xl" : "text-xl",
          light ? "text-white" : "text-brand",
        )}
      >
        Arba
      </span>
    </span>
  );
}
