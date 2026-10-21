import type { Requirement, Stage } from "@arba/api-client";
import { useTranslation } from "react-i18next";
import { cx } from "../components/ui";

/** Native select grouped by stage: fast, accessible, and a proper picker on phones. */
export function RequirementPicker({
  stages,
  requirements,
  value,
  onChange,
  disabled,
  className,
  label,
}: {
  stages: Stage[];
  requirements: Requirement[];
  value: string | null;
  onChange: (requirementId: string | null) => void;
  disabled?: boolean;
  className?: string;
  label?: string;
}) {
  const { t } = useTranslation();
  return (
    <select
      aria-label={label ?? t("inbox.fileTo")}
      value={value ?? ""}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value || null)}
      className={cx(
        "min-h-10 max-w-full rounded-xl border-2 border-ink bg-surface px-3 text-sm font-medium",
        "focus:shadow-[3px_3px_0_0_var(--color-accent)] focus:outline-none disabled:opacity-60",
        className,
      )}
    >
      <option value="">{value ? t("inbox.unfile") : t("inbox.chooseRequirement")}</option>
      {stages.map((stage) => (
        <optgroup key={stage.key} label={stage.title}>
          {requirements
            .filter((r) => r.stage === stage.key)
            .map((r) => (
              <option key={r.id} value={r.id}>
                {r.title}
              </option>
            ))}
        </optgroup>
      ))}
    </select>
  );
}
