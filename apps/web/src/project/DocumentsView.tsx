import type { DocumentOut, Requirement, Stage } from "@arba/api-client";
import { AnimatePresence, motion } from "motion/react";
import { useMemo, useRef, useState, type DragEvent } from "react";
import { useTranslation } from "react-i18next";
import { useCelebrate } from "../components/Celebrations";
import { Alert, Button, Spinner, cx } from "../components/ui";
import { $api, api, invalidateProjects } from "../lib/api";
import { UPLOAD_ACCEPT, fileIcon, formatBytes, formatDateTime } from "../lib/upload";
import { useErrorMessage } from "../lib/useErrorMessage";
import { RequirementPicker } from "./RequirementPicker";
import { useUploads, type UploadItem } from "./useUploads";

interface Props {
  projectId: string;
  projectName: string;
  canEdit: boolean;
  stages: Stage[];
  requirements: Requirement[];
}

export function DocumentsView({ projectId, projectName, canEdit, stages, requirements }: Props) {
  const { t } = useTranslation();
  const message = useErrorMessage();
  const documents = $api.useQuery("get", "/api/v1/projects/{project_id}/documents", {
    params: { path: { project_id: projectId } },
  });
  const { upload, items } = useUploads(projectId);

  const grouped = useMemo(() => {
    const byRequirement = new Map<string, DocumentOut[]>();
    const unfiled: DocumentOut[] = [];
    for (const d of documents.data ?? []) {
      if (!d.requirement_id) unfiled.push(d);
      else byRequirement.set(d.requirement_id, [...(byRequirement.get(d.requirement_id) ?? []), d]);
    }
    return { byRequirement, unfiled };
  }, [documents.data]);

  if (documents.error) return <Alert>{message(documents.error)}</Alert>;
  if (!documents.data) return <Spinner label={t("app.loading")} />;

  const rowProps = { projectId, canEdit, stages, requirements };

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="font-display text-2xl font-extrabold">
          {t("documents.count", { count: documents.data.length })}
        </h2>
        <ExportButton projectId={projectId} projectName={projectName} disabled={!documents.data.length} />
      </div>

      {canEdit && <DropZone onFiles={(files) => void upload(files)} />}
      <UploadProgress items={items} />

      {documents.data.length === 0 && (
        <p className="rounded-2xl border-2 border-dashed border-line p-8 text-center text-ink-soft">
          {t("documents.empty")}
        </p>
      )}

      <AnimatePresence>
        {grouped.unfiled.length > 0 && (
          <motion.section
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, height: 0 }}
            className="space-y-3 rounded-2xl border-2 border-ink bg-accent-soft p-4 shadow-[5px_5px_0_0_var(--color-ink)]"
          >
            <div>
              <h3 className="font-display text-xl font-bold">📥 {t("documents.unfiled")}</h3>
              <p className="text-sm text-ink-soft">{t("documents.unfiledHint")}</p>
            </div>
            <ul className="space-y-2">
              <AnimatePresence mode="popLayout">
                {grouped.unfiled.map((d) => (
                  <DocumentRow key={d.id} document={d} {...rowProps} highlight />
                ))}
              </AnimatePresence>
            </ul>
          </motion.section>
        )}
      </AnimatePresence>

      {stages.map((stage) => {
        const stageRequirements = requirements.filter(
          (r) => r.stage === stage.key && grouped.byRequirement.has(r.id),
        );
        if (!stageRequirements.length) return null;
        return (
          <section key={stage.key} className="space-y-3">
            <h3 className="font-display text-xl font-bold">{stage.title}</h3>
            {stageRequirements.map((r) => (
              <div key={r.id} className="rounded-2xl border-2 border-line bg-surface p-4">
                <h4 className="mb-2 font-bold">{r.title}</h4>
                <ul className="space-y-2">
                  <AnimatePresence mode="popLayout">
                    {grouped.byRequirement.get(r.id)!.map((d) => (
                      <DocumentRow key={d.id} document={d} {...rowProps} />
                    ))}
                  </AnimatePresence>
                </ul>
              </div>
            ))}
          </section>
        );
      })}
    </div>
  );
}

function DocumentRow({
  document: d,
  projectId,
  canEdit,
  stages,
  requirements,
  highlight,
}: {
  document: DocumentOut;
  highlight?: boolean;
} & Omit<Props, "projectName">) {
  const { t } = useTranslation();
  const message = useErrorMessage();
  const celebrate = useCelebrate();
  const path = { project_id: projectId, document_id: d.id };
  const file = $api.useMutation("patch", "/api/v1/projects/{project_id}/documents/{document_id}", {
    onSuccess: () => {
      celebrate.toast(t("documents.filedToast"), "🗂️");
      void invalidateProjects();
    },
  });
  const remove = $api.useMutation("delete", "/api/v1/projects/{project_id}/documents/{document_id}", {
    onSuccess: () => void invalidateProjects(),
  });

  return (
    <motion.li
      layout
      initial={{ opacity: 0, x: -16 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: 40, transition: { duration: 0.25 } }}
      className={cx(
        "flex flex-wrap items-center gap-3 rounded-xl border-2 p-2.5",
        highlight ? "border-ink/20 bg-surface" : "border-transparent bg-bg",
      )}
    >
      <span className="text-2xl" aria-hidden>
        {fileIcon(d.file_name, d.content_type)}
      </span>
      <div className="min-w-0 flex-1">
        <a href={d.download_url} className="block truncate font-medium hover:underline" title={t("documents.download")}>
          {d.file_name}
        </a>
        <div className="flex flex-wrap gap-x-2 text-xs text-ink-soft">
          <span dir="ltr">{formatBytes(d.size_bytes)}</span>
          <span>·</span>
          <span>{d.source === "email" ? `✉️ ${t("documents.fromEmail")}` : `⬆️ ${t("documents.uploaded")}`}</span>
          {d.uploaded_by_name && <span>· {d.uploaded_by_name}</span>}
          <span>· {formatDateTime(d.created_at)}</span>
        </div>
        {(file.error || remove.error) && (
          <div className="mt-1 text-xs text-danger">{message(file.error ?? remove.error)}</div>
        )}
      </div>
      {canEdit && (
        <div className="flex w-full items-center gap-2 sm:w-auto">
          <RequirementPicker
            stages={stages}
            requirements={requirements}
            value={d.requirement_id}
            disabled={file.isPending}
            className="min-w-0 flex-1 sm:w-56 sm:flex-none"
            onChange={(requirement_id) => file.mutate({ params: { path }, body: { requirement_id } })}
          />
          <Button
            size="sm"
            variant="danger"
            aria-label={t("documents.delete")}
            disabled={remove.isPending}
            onClick={() => {
              if (window.confirm(t("documents.confirmDelete", { name: d.file_name }))) {
                remove.mutate({ params: { path } });
              }
            }}
          >
            🗑️
          </Button>
        </div>
      )}
    </motion.li>
  );
}

export function DropZone({ onFiles, compact }: { onFiles: (files: File[]) => void; compact?: boolean }) {
  const { t } = useTranslation();
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const drop = (e: DragEvent) => {
    e.preventDefault();
    setOver(false);
    onFiles([...e.dataTransfer.files]);
  };
  return (
    <>
    <motion.button
      type="button"
      onClick={() => input.current?.click()}
      onDragOver={(e) => {
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={drop}
      animate={{ scale: over ? 1.02 : 1 }}
      className={cx(
        "flex w-full flex-col items-center justify-center gap-2 rounded-2xl border-2 border-dashed text-center transition-colors",
        compact ? "p-4" : "p-8",
        over ? "border-accent bg-accent-soft" : "border-ink/30 bg-surface hover:border-ink hover:bg-surface",
      )}
    >
      <motion.span
        className="text-4xl"
        animate={over ? { y: [0, -8, 0] } : { y: 0 }}
        transition={{ repeat: over ? Infinity : 0, duration: 0.8 }}
      >
        📤
      </motion.span>
      <span className="font-display text-lg font-bold">{t("documents.drop")}</span>
      <span className="text-sm text-ink-soft">{t("documents.hint")}</span>
    </motion.button>
    <input
      ref={input}
      type="file"
      multiple
      accept={UPLOAD_ACCEPT}
      className="hidden"
      onChange={(e) => {
        onFiles([...(e.target.files ?? [])]);
        e.target.value = "";
      }}
    />
    </>
  );
}

export function UploadProgress({ items }: { items: UploadItem[] }) {
  return (
    <ul className="space-y-2">
      <AnimatePresence>
        {items.map((item) => (
          <motion.li
            key={item.id}
            layout
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95 }}
            className="rounded-xl border-2 border-ink/10 bg-surface p-2.5 text-sm"
          >
            <div className="flex items-center justify-between gap-3">
              <span className="truncate font-medium">{item.name}</span>
              <span className={item.error ? "text-danger" : "text-ink-soft"}>
                {item.error ?? (item.progress >= 1 ? "✓" : `${Math.round(item.progress * 100)}%`)}
              </span>
            </div>
            {!item.error && (
              <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-line">
                <motion.div
                  className="h-full rounded-full bg-accent"
                  initial={{ width: 0 }}
                  animate={{ width: `${item.progress * 100}%` }}
                  transition={{ ease: "easeOut" }}
                />
              </div>
            )}
          </motion.li>
        ))}
      </AnimatePresence>
    </ul>
  );
}

function ExportButton({ projectId, projectName, disabled }: { projectId: string; projectName: string; disabled: boolean }) {
  const { t } = useTranslation();
  const message = useErrorMessage();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();

  // The export needs the access token, so fetch it and hand the browser a blob link.
  const download = async () => {
    setBusy(true);
    setError(undefined);
    const { data, error: failure } = await api.fetchClient.GET(
      "/api/v1/projects/{project_id}/documents/export",
      { params: { path: { project_id: projectId } }, parseAs: "blob" },
    );
    setBusy(false);
    if (!data) return setError(message(failure));
    const url = URL.createObjectURL(data as Blob);
    const link = Object.assign(document.createElement("a"), { href: url, download: `${projectName} - Arba.zip` });
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="flex flex-col items-end gap-1">
      <Button variant="secondary" size="sm" disabled={disabled || busy} onClick={() => void download()}>
        🗂️ {busy ? t("documents.exporting") : t("documents.downloadAll")}
      </Button>
      {error && <span className="text-xs text-danger">{error}</span>}
    </div>
  );
}
