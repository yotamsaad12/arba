import type { Locality, PermitFields, ProjectFeature } from "@arba/api-client";
import { AnimatePresence, motion } from "motion/react";
import { useEffect, useRef, useState, type DragEvent, type ReactNode } from "react";
import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router";
import { Alert, BrutalCard, Button, Card, Field, Input, Spinner, cx } from "../components/ui";
import { $api, api, invalidateProjects } from "../lib/api";
import { uploadFile } from "../lib/upload";
import { useErrorMessage } from "../lib/useErrorMessage";
import { FeatureChips } from "../project/Form4View";
import { LocalityPicker } from "../project/LocalityPicker";
import { STAGES, STAGE_ICON, type StageKey } from "../scene/model";

// Stages someone can say they are in now. Green building runs alongside, so it isn't one.
const CURRENT_STAGES = STAGES.filter((s) => s !== "green");

type Step = "permit" | "details";

interface Details {
  name: string;
  address: string;
  floors: number;
  gush: string;
  helka: string;
  plot_number: string;
  buildings: number;
  units: string;
  template_id: string;
  permit_number: string;
  permit_request_number: string;
  permit_issue_date: string;
  permit_valid_until: string;
  permit_committee: string;
}

const EMPTY: Details = {
  name: "",
  address: "",
  floors: 1,
  gush: "",
  helka: "",
  plot_number: "",
  buildings: 1,
  units: "",
  template_id: "",
  permit_number: "",
  permit_request_number: "",
  permit_issue_date: "",
  permit_valid_until: "",
  permit_committee: "",
};

export function NewProjectPage() {
  const { t } = useTranslation();
  const message = useErrorMessage();
  const navigate = useNavigate();
  const templates = $api.useQuery("get", "/api/v1/templates");
  const [step, setStep] = useState<Step>("permit");
  const [file, setFile] = useState<File | null>(null);
  const [reading, setReading] = useState(false);
  const [readResult, setReadResult] = useState<{ fields: PermitFields; source: string } | null>(null);
  const [locality, setLocality] = useState<Locality | null>(null);
  const [creating, setCreating] = useState(false);
  const [nowAt, setNowAt] = useState<StageKey | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [features, setFeatures] = useState<ReadonlySet<ProjectFeature>>(new Set());
  const form = useForm<Details>({ defaultValues: EMPTY });
  const developer = templates.data?.find((tpl) => tpl.id === form.watch("template_id"))?.client_type === "business";

  useEffect(() => {
    const only = templates.data?.length === 1 ? templates.data[0] : undefined;
    if (only && !form.getValues("template_id")) form.setValue("template_id", only.id);
  }, [templates.data, form]);

  const readPermit = async (pdf: File) => {
    setFile(pdf);
    setReading(true);
    setError(null);
    const body = new FormData();
    body.append("file", pdf);
    const { data, error: failure } = await api.fetchClient.POST("/api/v1/permits/extract", {
      body: body as never,
      bodySerializer: () => body,
    });
    setReading(false);
    if (!data) {
      setError(message(failure));
      return;
    }
    const f = data.fields;
    setReadResult({ fields: f, source: data.source });
    if (data.locality) setLocality(data.locality);
    form.reset({
      ...form.getValues(),
      permit_number: f.permit_number ?? "",
      permit_request_number: f.request_number ?? "",
      permit_issue_date: f.issue_date ?? "",
      permit_valid_until: f.valid_until ?? "",
      permit_committee: f.committee ?? "",
      address: f.address ?? "",
      gush: f.gush ?? "",
      helka: f.helka ?? "",
      name: data.locality ? `הבית ב${data.locality.name}` : "",
    });
  };

  const create = form.handleSubmit(async (v) => {
    setCreating(true);
    setError(null);
    const orNull = (s: string) => s.trim() || null;
    const created = await api.fetchClient.POST("/api/v1/projects", {
      body: {
        name: v.name,
        template_id: v.template_id,
        locality_code: locality?.code ?? null,
        address: orNull(v.address),
        floors: Number(v.floors) || 1,
        gush: orNull(v.gush),
        helka: orNull(v.helka),
        plot_number: orNull(v.plot_number),
        buildings: developer ? Number(v.buildings) || 1 : 1,
        units: developer && v.units ? Number(v.units) : null,
        features: [...features],
        permit_number: orNull(v.permit_number),
        permit_request_number: orNull(v.permit_request_number),
        permit_issue_date: orNull(v.permit_issue_date),
        permit_valid_until: orNull(v.permit_valid_until),
        permit_committee: orNull(v.permit_committee),
      },
    });
    if (!created.data) {
      setCreating(false);
      setError(message(created.error));
      return;
    }
    const projectId = created.data.id;
    // File the permit under its requirement, then let Arba check it.
    if (file) {
      const permit = await api.fetchClient.GET("/api/v1/projects/{project_id}/permit", {
        params: { path: { project_id: projectId } },
      });
      try {
        await uploadFile(projectId, file, permit.data?.requirement_id ?? null, () => {});
        await api.fetchClient.POST("/api/v1/projects/{project_id}/permit/check", {
          params: { path: { project_id: projectId } },
        });
      } catch {
        // The project exists; the banner there lets them upload the permit again.
      }
    }
    // Already under way: mark what's behind them done, then gather what they already have.
    if (nowAt) {
      if (nowAt !== "pre") {
        await api.fetchClient.POST("/api/v1/projects/{project_id}/catch-up", {
          params: { path: { project_id: projectId } },
          body: { stage: nowAt },
        });
      }
      await invalidateProjects();
      void navigate(`/projects/${projectId}/import`);
      return;
    }
    await invalidateProjects();
    void navigate(`/projects/${projectId}`);
  });

  if (templates.isPending) return <Spinner label={t("app.loading")} />;
  const field = (name: keyof Details) => form.register(name);

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <Link to="/" className="text-sm text-brand">
        → {t("app.back")}
      </Link>
      <Stepper step={step} />

      <AnimatePresence mode="wait">
        {step === "permit" ? (
          <motion.div key="permit" initial={{ opacity: 0, x: 30 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -30 }} className="space-y-5">
            <div>
              <h1 className="font-display text-3xl font-extrabold">📜 {t("permit.stepTitle")}</h1>
              <p className="text-ink-soft">{t("permit.stepHint")}</p>
            </div>

            {!readResult && !reading && <PermitDrop onFile={(f) => void readPermit(f)} />}
            {reading && <Reading name={file?.name ?? ""} />}

            {readResult && (
              <BrutalCard className="space-y-4">
                <div className="flex items-center gap-3">
                  <span className="text-3xl">📄</span>
                  <div className="min-w-0 flex-1">
                    <div className="truncate font-bold">{file?.name}</div>
                    <button className="text-xs font-bold text-accent-strong" onClick={() => setReadResult(null)}>
                      {t("permit.replaceFile")} ↺
                    </button>
                  </div>
                </div>
                {!readResult.fields.is_permit ? (
                  <Alert tone="warning">{t("permit.notPermit")}</Alert>
                ) : (
                  <p className="text-sm font-medium">
                    ✨ {readResult.source === "claude" ? t("permit.readByClaude") : t("permit.readByRules")}
                  </p>
                )}
                <div className="grid gap-3 sm:grid-cols-2">
                  <Field label={t("permit.number")}>
                    <Input dir="ltr" {...field("permit_number")} />
                  </Field>
                  <Field label={t("permit.requestNumber")}>
                    <Input dir="ltr" {...field("permit_request_number")} />
                  </Field>
                  <Field label={t("permit.issueDate")}>
                    <Input type="date" {...field("permit_issue_date")} />
                  </Field>
                  <Field label={t("permit.validUntil")}>
                    <Input type="date" {...field("permit_valid_until")} />
                  </Field>
                </div>
                <Field label={t("permit.committee")}>
                  <Input {...field("permit_committee")} />
                </Field>
              </BrutalCard>
            )}

            <Card className="space-y-2">
              <Field label={t("permit.locality")} hint={t("permit.localityHint")}>
                <LocalityPicker value={locality} onChange={setLocality} />
              </Field>
            </Card>

            {!readResult && !reading && (
              <Card className="space-y-2 border-dashed bg-transparent">
                <div className="font-bold">🤔 {t("permit.noPermitTitle")}</div>
                <p className="text-sm text-ink-soft">{t("permit.noPermitHint")}</p>
              </Card>
            )}
            {error && <Alert>{error}</Alert>}

            <div className="flex flex-wrap gap-3">
              <Button disabled={reading || !locality} onClick={() => setStep("details")}>
                {t("permit.next")} ←
              </Button>
              {!readResult && (
                <Button variant="secondary" disabled={reading || !locality} onClick={() => setStep("details")}>
                  {t("permit.noFile")}
                </Button>
              )}
            </div>
          </motion.div>
        ) : (
          <motion.form
            key="details"
            initial={{ opacity: 0, x: 30 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -30 }}
            className="space-y-5"
            onSubmit={(e) => void create(e)}
          >
            <h1 className="font-display text-3xl font-extrabold">🏠 {t("permit.detailsTitle")}</h1>
            <Card className="space-y-4">
              <Field label={t("projects.name")}>
                <Input placeholder={t("projects.namePlaceholder")} {...form.register("name", { required: true })} />
              </Field>
              <Field label={t("projects.address")}>
                <Input autoComplete="street-address" {...field("address")} />
              </Field>
              <Field label={t("projects.floors")} hint={t("projects.floorsHint")}>
                <Input type="number" inputMode="numeric" min={1} max={60} {...form.register("floors", { valueAsNumber: true })} />
              </Field>
              <div className="grid grid-cols-3 gap-3">
                <Field label={t("projects.gush")}>
                  <Input inputMode="numeric" {...field("gush")} />
                </Field>
                <Field label={t("projects.helka")}>
                  <Input inputMode="numeric" {...field("helka")} />
                </Field>
                <Field label={t("form4.plot")}>
                  <Input {...field("plot_number")} />
                </Field>
              </div>
            </Card>
            <Card className="space-y-3">
              <div>
                <div className="font-display text-lg font-extrabold">🚧 {t("catchup.whereTitle")}</div>
                <p className="text-sm text-ink-soft">{t("catchup.whereHint")}</p>
              </div>
              <div className="flex flex-wrap gap-2">
                <StageChip active={nowAt === null} onClick={() => setNowAt(null)}>
                  ✨ {t("catchup.notStarted")}
                </StageChip>
                {CURRENT_STAGES.map((stage) => (
                  <StageChip key={stage} active={nowAt === stage} onClick={() => setNowAt(stage)}>
                    {STAGE_ICON[stage]} {t(`stage.${stage}`)}
                  </StageChip>
                ))}
              </div>
            </Card>
            <fieldset className="space-y-2">
              <legend className="mb-1.5 text-sm font-medium">{t("projects.template")}</legend>
              {templates.data?.map((tpl) => (
                <label
                  key={tpl.id}
                  className={cx(
                    "flex cursor-pointer gap-3 rounded-xl border-2 bg-surface p-4",
                    form.watch("template_id") === tpl.id ? "border-ink bg-accent-soft" : "border-line",
                  )}
                >
                  <input type="radio" value={tpl.id} className="mt-1 accent-ink" {...form.register("template_id", { required: true })} />
                  <span>
                    <span className="block font-medium">{tpl.name}</span>
                    <span className="block text-sm text-ink-soft">{tpl.description}</span>
                  </span>
                </label>
              ))}
            </fieldset>
            {developer && (
              <Card className="grid grid-cols-2 gap-3">
                <Field label={t("form4.buildings")} hint={t("projects.buildingsHint")}>
                  <Input type="number" inputMode="numeric" min={1} max={50} {...form.register("buildings", { valueAsNumber: true })} />
                </Field>
                <Field label={t("form4.units")}>
                  <Input type="number" inputMode="numeric" min={1} {...field("units")} />
                </Field>
              </Card>
            )}
            <Card className="space-y-3">
              <div>
                <div className="font-display text-lg font-extrabold">🧩 {t("form4.features")}</div>
                <p className="text-sm text-ink-soft">{t("form4.featuresHint")}</p>
              </div>
              <FeatureChips
                value={features}
                onToggle={(feature) =>
                  setFeatures((current) => {
                    const next = new Set(current);
                    if (next.has(feature)) next.delete(feature);
                    else next.add(feature);
                    return next;
                  })
                }
              />
            </Card>
            {error && <Alert>{error}</Alert>}
            <div className="flex flex-wrap gap-3">
              <Button type="submit" disabled={creating}>
                {creating ? t("permit.creating") : t("projects.create")}
              </Button>
              <Button type="button" variant="secondary" onClick={() => setStep("permit")}>
                {t("permit.back")}
              </Button>
            </div>
          </motion.form>
        )}
      </AnimatePresence>
    </div>
  );
}

function StageChip({ active, onClick, children }: { active: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <motion.button
      type="button"
      onClick={onClick}
      whileTap={{ scale: 0.94 }}
      animate={{ y: active ? -2 : 0 }}
      className={cx(
        "rounded-full border-2 px-3 py-1.5 text-sm font-bold",
        active ? "border-ink bg-accent shadow-[2px_2px_0_0_var(--color-ink)]" : "border-line bg-surface hover:border-ink",
      )}
    >
      {children}
    </motion.button>
  );
}

function Stepper({ step }: { step: Step }) {
  const { t } = useTranslation();
  const steps: [Step, string][] = [
    ["permit", t("permit.stepTitle")],
    ["details", t("permit.detailsTitle")],
  ];
  return (
    <ol className="flex items-center gap-2 text-sm">
      {steps.map(([key, label], i) => (
        <li key={key} className="flex items-center gap-2">
          <span
            className={cx(
              "grid size-7 place-items-center rounded-full border-2 border-ink font-display font-bold",
              step === key ? "bg-accent" : i === 0 && step === "details" ? "bg-success-soft" : "bg-surface",
            )}
          >
            {i === 0 && step === "details" ? "✓" : i + 1}
          </span>
          <span className={step === key ? "font-bold" : "text-ink-soft"}>{label}</span>
          {i < steps.length - 1 && <span className="mx-1 h-0.5 w-8 bg-line" />}
        </li>
      ))}
    </ol>
  );
}

function PermitDrop({ onFile }: { onFile: (file: File) => void }): ReactNode {
  const { t } = useTranslation();
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const take = (files: FileList | null) => {
    const pdf = files?.[0];
    if (pdf) onFile(pdf);
  };
  return (
    <>
      <motion.button
        type="button"
        onClick={() => input.current?.click()}
        onDragOver={(e: DragEvent) => {
          e.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={(e: DragEvent) => {
          e.preventDefault();
          setOver(false);
          take(e.dataTransfer.files);
        }}
        animate={{ scale: over ? 1.02 : 1 }}
        className={cx(
          "flex w-full flex-col items-center gap-3 rounded-3xl border-2 border-dashed p-10 text-center",
          over ? "border-accent bg-accent-soft" : "border-ink/40 bg-surface hover:border-ink",
        )}
      >
        <motion.span className="text-6xl" animate={{ y: [0, -8, 0] }} transition={{ duration: 2, repeat: Infinity }}>
          📜
        </motion.span>
        <span className="font-display text-xl font-bold">{t("permit.drop")}</span>
      </motion.button>
      <input ref={input} type="file" accept="application/pdf,.pdf" className="hidden" onChange={(e) => take(e.target.files)} />
    </>
  );
}

function Reading({ name }: { name: string }) {
  const { t } = useTranslation();
  return (
    <BrutalCard className="flex flex-col items-center gap-4 py-10">
      <div className="relative h-32 w-24 overflow-hidden rounded-lg border-2 border-ink bg-surface">
        {[...Array(7)].map((_, i) => (
          <span key={i} className="mx-3 mt-3 block h-1.5 rounded bg-line" style={{ width: `${55 + ((i * 17) % 35)}%` }} />
        ))}
        <motion.span
          className="absolute inset-x-0 h-6 bg-gradient-to-b from-transparent via-accent/60 to-transparent"
          animate={{ top: ["-10%", "100%"] }}
          transition={{ duration: 1.4, repeat: Infinity, ease: "linear" }}
        />
      </div>
      <div className="font-display text-lg font-bold">✨ {t("permit.reading")}</div>
      <div className="text-sm text-ink-soft">{name}</div>
    </BrutalCard>
  );
}
