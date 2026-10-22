import type { Locality } from "@arba/api-client";
import { AnimatePresence, motion } from "motion/react";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Input, cx } from "../components/ui";
import { $api } from "../lib/api";

/** Search-as-you-type over the official localities list, showing the responsible committee. */
export function LocalityPicker({
  value,
  onChange,
  invalid,
}: {
  value: Locality | null;
  onChange: (locality: Locality | null) => void;
  invalid?: boolean;
}) {
  const { t } = useTranslation();
  const [text, setText] = useState(value?.name ?? "");
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => setText(value?.name ?? ""), [value]);
  // Debounce: search 250ms after typing stops.
  useEffect(() => {
    const id = window.setTimeout(() => setQuery(text.trim()), 250);
    return () => window.clearTimeout(id);
  }, [text]);
  useEffect(() => {
    const close = (e: MouseEvent) => !box.current?.contains(e.target as Node) && setOpen(false);
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  const results = $api.useQuery(
    "get",
    "/api/v1/directory/localities",
    { params: { query: { q: query } } },
    { enabled: open && query.length >= 2 && query !== value?.name },
  );

  return (
    <div ref={box} className="relative">
      <Input
        value={text}
        aria-invalid={invalid}
        placeholder={t("permit.localityPlaceholder")}
        onFocus={() => setOpen(true)}
        onChange={(e) => {
          setText(e.target.value);
          setOpen(true);
          if (value) onChange(null);
        }}
      />
      {value?.committee && (
        <p className="mt-1 text-xs text-ink-soft">
          🏛️{" "}
          {t(value.committee_source === "assumed" ? "permit.assumedCommittee" : "permit.officialCommittee", {
            name: value.committee,
          })}
        </p>
      )}
      <AnimatePresence>
        {open && (results.data?.length ?? 0) > 0 && (
          <motion.ul
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="absolute inset-x-0 top-full z-20 mt-1 max-h-72 overflow-y-auto rounded-xl border-2 border-ink bg-surface shadow-[4px_4px_0_0_var(--color-ink)]"
          >
            {results.data!.map((loc) => (
              <li key={loc.code}>
                <button
                  type="button"
                  onClick={() => {
                    onChange(loc);
                    setText(loc.name);
                    setOpen(false);
                  }}
                  className={cx("block w-full px-3 py-2 text-start hover:bg-accent-soft", loc.code === value?.code && "bg-accent-soft")}
                >
                  <span className="font-medium">{loc.name}</span>
                  {loc.municipality && loc.municipality !== loc.name && (
                    <span className="text-sm text-ink-soft"> · {loc.municipality}</span>
                  )}
                  {loc.committee && (
                    <span className="block text-xs text-ink-soft">
                      {t(loc.committee_source === "assumed" ? "permit.assumedCommittee" : "permit.officialCommittee", {
                        name: loc.committee,
                      })}
                    </span>
                  )}
                </button>
              </li>
            ))}
          </motion.ul>
        )}
      </AnimatePresence>
    </div>
  );
}
