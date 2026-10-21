import type { Project } from "@arba/api-client";
import { motion } from "motion/react";
import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { Alert, ProgressBar, Spinner } from "../components/ui";
import { $api } from "../lib/api";
import { useErrorMessage } from "../lib/useErrorMessage";
import { ConstructionScene } from "../scene/ConstructionScene";
import { sceneModel } from "../scene/model";
import { useFocusLabel } from "../scene/useFocusLabel";

export function ProjectsPage() {
  const { t } = useTranslation();
  const message = useErrorMessage();
  const { data: projects, error } = $api.useQuery("get", "/api/v1/projects");

  if (error) return <Alert>{message(error)}</Alert>;
  if (!projects) return <Spinner label={t("app.loading")} />;

  return (
    <div className="space-y-6">
      <h1 className="font-display text-3xl font-extrabold tracking-tight sm:text-4xl">
        {t("projects.title")}
      </h1>
      {projects.length === 0 && <p className="text-lg text-ink-soft">{t("projects.empty")}</p>}
      <div className="grid gap-6 sm:grid-cols-2">
        {projects.map((p, i) => (
          <motion.div
            key={p.id}
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.08, duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
          >
            <ProjectCard project={p} />
          </motion.div>
        ))}
        <motion.div
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: projects.length * 0.08, duration: 0.5 }}
        >
          <Link
            to="/projects/new"
            className="group flex h-full min-h-64 flex-col items-center justify-center gap-3 rounded-2xl border-2 border-dashed border-ink/40 p-6 text-center transition-all hover:border-ink hover:bg-surface hover:shadow-[5px_5px_0_0_var(--color-ink)]"
          >
            <span className="grid size-14 place-items-center rounded-full border-2 border-ink bg-accent text-3xl font-bold text-white transition-transform group-hover:rotate-90">
              +
            </span>
            <span className="font-display text-xl font-bold">{t("projects.new")}</span>
            <span className="text-sm text-ink-soft">{t("projects.newHint")}</span>
          </Link>
        </motion.div>
      </div>
    </div>
  );
}

function ProjectCard({ project: p }: { project: Project }) {
  const { t } = useTranslation();
  const model = useMemo(() => sceneModel(p.build, p.floors), [p.build, p.floors]);
  const focus = useFocusLabel(model);
  const percent = Math.round(model.overall * 100);

  return (
    <Link
      to={`/projects/${p.id}`}
      className="group block overflow-hidden rounded-2xl border-2 border-ink bg-surface shadow-[5px_5px_0_0_var(--color-ink)] transition-all duration-200 hover:-translate-y-1 hover:shadow-[7px_9px_0_0_var(--color-ink)]"
    >
      <div className="aspect-[5/3] overflow-hidden border-b-2 border-ink">
        <ConstructionScene
          model={model}
          label={t("scene.label")}
          className="size-full transition-transform duration-500 group-hover:scale-105"
        />
      </div>
      <div className="space-y-3 p-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="font-display text-xl font-bold">{p.name}</h2>
            <p className="text-sm text-ink-soft">
              {[p.address, p.municipality].filter(Boolean).join(", ")}
            </p>
          </div>
          <span className="font-display text-2xl font-extrabold text-accent-strong">{percent}%</span>
        </div>
        <ProgressBar done={p.build.progress.done} total={p.build.progress.total} />
        {focus && (
          <span className="inline-flex items-center gap-1.5 rounded-full bg-accent-soft px-2.5 py-1 text-xs font-bold">
            <span className="size-1.5 animate-pulse rounded-full bg-accent-strong" />
            {focus}
          </span>
        )}
      </div>
    </Link>
  );
}
