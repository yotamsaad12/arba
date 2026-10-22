import type { CatchUpReport, ProjectDetail, ReportItem, ScanInfo } from "@arba/api-client";
import { AnimatePresence, motion } from "motion/react";
import { useEffect, useRef, useState, type DragEvent } from "react";
import { useTranslation } from "react-i18next";
import { Link, useParams, useSearchParams } from "react-router";
import { useCelebrate } from "../components/Celebrations";
import { Alert, Badge, BrutalCard, Button, Card, Spinner, cx } from "../components/ui";
import { $api, api, invalidateProjects, queryClient } from "../lib/api";
import { UPLOAD_ACCEPT, uploadFile } from "../lib/upload";
import { useErrorMessage } from "../lib/useErrorMessage";
import { STAGE_ICON, isStageKey } from "../scene/model";

const REPORT = "/api/v1/projects/{project_id}/catch-up/report";

/** Bringing an existing project's history into Arba: mailbox scan, bulk upload, and the gaps. */
export function ImportPage() {
  const { projectId = "" } = useParams();
  const { t } = useTranslation();
  const [search] = useSearchParams();
  const path = { params: { path: { project_id: projectId } } };
  const project = $api.useQuery("get", "/api/v1/projects/{project_id}", path);
  // Arba keeps sorting for a little while after uploads; poll during that window too.
  const [settleUntil, setSettleUntil] = useState(0);
  const report = $api.useQuery("get", REPORT, path, {
    refetchInterval: (q) =>
      q.state.data?.state === "scanning" || Date.now() < settleUntil ? 1500 : false,
  });
  const notice = search.get("mailbox");

  if (!project.data || !report.data) return <Spinner label={t("app.loading")} />;
  const r = report.data;

  return (
    <div className="mx-auto max-w-5xl space-y-8">
      <Link to={`/projects/${projectId}`} className="text-sm text-brand">
        → {project.data.name}
      </Link>
      <header className="space-y-2">
        <motion.h1
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          className="font-display text-3xl font-extrabold sm:text-4xl"
        >
          🗂️ {t("catchup.title")}
        </motion.h1>
        <p className="max-w-2xl text-ink-soft">{t("catchup.hint")}</p>
      </header>
      {notice && <Alert tone="warning">{t(notice === "busy" ? "catchup.busy" : "catchup.denied")}</Alert>}

      <AnimatePresence mode="wait">
        {r.state === "scanning" && r.scan ? (
          <ScanRadar key="scan" scan={r.scan} />
        ) : (
          <motion.div key="sources" initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="grid gap-5 md:grid-cols-2">
            <MailCard project={project.data} report={r} />
            <FilesCard projectId={projectId} onUploaded={() => setSettleUntil(Date.now() + 20_000)} />
          </motion.div>
        )}
      </AnimatePresence>

      {r.state === "ready" && <Results projectId={projectId} report={r} />}
    </div>
  );
}

// --- Sources --------------------------------------------------------------------------

function MailCard({ project: p, report }: { project: ProjectDetail; report: CatchUpReport }) {
  const { t } = useTranslation();
  const message = useErrorMessage();
  const connect = $api.useQuery("get", "/api/v1/projects/{project_id}/mailbox/connect", {
    params: { path: { project_id: p.id } },
  });
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const terms = [
    p.permit.number && `${t("permit.number")} ${p.permit.number}`,
    p.gush && `${t("projects.gush")} ${p.gush}`,
    p.address,
    t("directory.title") + ` · ${p.municipality}`,
  ].filter(Boolean);

  const start = async () => {
    const provider = connect.data?.provider;
    if (provider === "gmail" && connect.data?.url) {
      window.location.href = connect.data.url;
      return;
    }
    setStarting(true);
    setError(null);
    const { error: failure } = await api.fetchClient.POST("/api/v1/projects/{project_id}/mailbox/scans", {
      params: { path: { project_id: p.id } },
    });
    if (failure) setError(message(failure));
    await queryClient.invalidateQueries({ queryKey: ["get", REPORT] });
    setStarting(false);
  };

  return (
    <BrutalCard className="flex flex-col gap-4">
      <div className="flex items-center gap-3">
        <motion.span
          className="text-4xl"
          animate={{ y: [0, -5, 0], rotate: [0, -6, 6, 0] }}
          transition={{ duration: 3, repeat: Infinity }}
        >
          📬
        </motion.span>
        <h2 className="font-display text-2xl font-extrabold">{t("catchup.mailTitle")}</h2>
      </div>
      <p className="text-sm">{t("catchup.mailHint")}</p>
      <div>
        <div className="mb-1.5 text-xs font-bold text-ink-soft">{t("catchup.searchFor")}</div>
        <div className="flex flex-wrap gap-1.5">
          {terms.map((term, i) => (
            <motion.span
              key={String(term)}
              initial={{ opacity: 0, scale: 0.8 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ delay: 0.1 + i * 0.08 }}
              className="rounded-full border-2 border-ink bg-accent-soft px-2.5 py-0.5 text-xs font-bold"
            >
              🔎 {term}
            </motion.span>
          ))}
        </div>
      </div>
      <p className="rounded-xl bg-success-soft px-3 py-2 text-xs font-medium text-success">🔒 {t("catchup.mailPrivacy")}</p>
      {report.scan?.status === "failed" && <Alert>{t("catchup.scanFailed")}</Alert>}
      {error && <Alert>{error}</Alert>}
      <div className="mt-auto">
        {connect.data?.provider ? (
          <Button disabled={starting} onClick={() => void start()}>
            {connect.data.provider === "gmail" ? `✉️ ${t("catchup.connectGmail")}` : `🧪 ${t("catchup.simulate")}`}
          </Button>
        ) : (
          connect.isSuccess && <p className="text-sm text-ink-soft">{t("catchup.noProvider")}</p>
        )}
      </div>
    </BrutalCard>
  );
}

function FilesCard({ projectId, onUploaded }: { projectId: string; onUploaded: () => void }) {
  const { t } = useTranslation();
  const { toast } = useCelebrate();
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const [progress, setProgress] = useState<{ done: number; total: number } | null>(null);

  const upload = async (files: FileList | null) => {
    const list = Array.from(files ?? []);
    if (!list.length) return;
    setProgress({ done: 0, total: list.length });
    let ok = 0;
    for (const [i, file] of list.entries()) {
      try {
        await uploadFile(projectId, file, null, () => {});
        ok += 1;
      } catch {
        // Skipped (type or size); the rest still go up.
      }
      setProgress({ done: i + 1, total: list.length });
    }
    setProgress(null);
    toast(t("catchup.uploaded", { count: ok }), "📂");
    onUploaded();
    await invalidateProjects();
  };

  return (
    <Card className="flex flex-col gap-4 border-2 border-ink">
      <div className="flex items-center gap-3">
        <span className="text-4xl">📂</span>
        <h2 className="font-display text-2xl font-extrabold">{t("catchup.filesTitle")}</h2>
      </div>
      <p className="text-sm">{t("catchup.filesHint")}</p>
      <motion.button
        type="button"
        disabled={progress !== null}
        onClick={() => input.current?.click()}
        onDragOver={(e: DragEvent) => {
          e.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={(e: DragEvent) => {
          e.preventDefault();
          setOver(false);
          void upload(e.dataTransfer.files);
        }}
        animate={{ scale: over ? 1.03 : 1 }}
        className={cx(
          "relative mt-auto flex min-h-36 flex-col items-center justify-center gap-2 overflow-hidden rounded-2xl border-2 border-dashed p-6",
          over ? "border-accent bg-accent-soft" : "border-ink/40 hover:border-ink",
        )}
      >
        {progress ? (
          <>
            <motion.div
              className="absolute inset-y-0 start-0 bg-accent-soft"
              animate={{ width: `${(progress.done / progress.total) * 100}%` }}
            />
            <span className="relative font-bold">{t("catchup.uploading", progress)}</span>
          </>
        ) : (
          <>
            <div className="flex -space-x-3 text-3xl rtl:space-x-reverse">
              {["📄", "🖼️", "📑"].map((icon, i) => (
                <motion.span
                  key={icon}
                  animate={{ y: [0, -6, 0] }}
                  transition={{ duration: 1.8, repeat: Infinity, delay: i * 0.25 }}
                >
                  {icon}
                </motion.span>
              ))}
            </div>
            <span className="font-bold">{t("catchup.filesDrop")}</span>
          </>
        )}
      </motion.button>
      <input
        ref={input}
        type="file"
        multiple
        accept={UPLOAD_ACCEPT}
        className="hidden"
        onChange={(e) => {
          const files = e.target.files;
          void upload(files).then(() => (e.target.value = ""));
        }}
      />
    </Card>
  );
}

// --- Scanning -------------------------------------------------------------------------

function ScanRadar({ scan }: { scan: ScanInfo }) {
  const { t } = useTranslation();
  const flying = [...Array(8)].map((_, i) => {
    const angle = (i / 8) * Math.PI * 2;
    return { x: Math.cos(angle) * 170, y: Math.sin(angle) * 120, delay: i * 0.35 };
  });
  return (
    <motion.section
      initial={{ opacity: 0, scale: 0.96 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.96 }}
      className="relative overflow-hidden rounded-3xl border-2 border-ink bg-ink p-8 text-white shadow-[6px_6px_0_0_var(--color-accent)]"
    >
      <div className="relative mx-auto grid h-64 max-w-md place-items-center">
        {[0, 1, 2].map((i) => (
          <motion.span
            key={i}
            className="absolute size-40 rounded-full border-2 border-accent"
            initial={{ scale: 0.4, opacity: 0.9 }}
            animate={{ scale: 2.2, opacity: 0 }}
            transition={{ duration: 2.4, repeat: Infinity, delay: i * 0.8, ease: "easeOut" }}
          />
        ))}
        {flying.map((f, i) => (
          <motion.span
            key={i}
            className="absolute text-2xl"
            initial={{ x: f.x, y: f.y, opacity: 0, scale: 1 }}
            animate={{ x: 0, y: 0, opacity: [0, 1, 1, 0], scale: [1, 1, 0.4] }}
            transition={{ duration: 2.8, repeat: Infinity, delay: f.delay, ease: "easeIn" }}
          >
            ✉️
          </motion.span>
        ))}
        <motion.span
          className="relative z-10 grid size-24 place-items-center rounded-3xl border-2 border-white bg-accent text-5xl"
          animate={{ rotate: [0, -4, 4, 0] }}
          transition={{ duration: 1.2, repeat: Infinity }}
        >
          🗂️
        </motion.span>
      </div>
      <div className="relative text-center">
        <div className="font-display text-2xl font-extrabold">{t("catchup.scanning")}</div>
        <div className="text-sm opacity-75" dir="auto">
          {t("catchup.scanningAccount", { email: scan.account_email })}
        </div>
      </div>
      <dl className="relative mt-6 grid grid-cols-3 gap-3 text-center">
        {(
          [
            ["statFound", scan.messages_found],
            ["statImported", scan.messages_imported],
            ["statFiles", scan.files_imported],
          ] as const
        ).map(([label, value]) => (
          <div key={label} className="rounded-2xl bg-white/10 p-3">
            <motion.dd
              key={value}
              initial={{ scale: 1.4, color: "var(--color-accent)" }}
              animate={{ scale: 1, color: "#ffffff" }}
              className="font-display text-3xl font-extrabold"
            >
              {value}
            </motion.dd>
            <dt className="text-xs opacity-75">{t(`catchup.${label}`)}</dt>
          </div>
        ))}
      </dl>
    </motion.section>
  );
}

// --- Results --------------------------------------------------------------------------

function Results({ projectId, report: r }: { projectId: string; report: CatchUpReport }) {
  const { t } = useTranslation();
  const message = useErrorMessage();
  const { toast, burst } = useCelebrate();
  const approve = $api.useMutation("post", "/api/v1/projects/{project_id}/suggestions/accept-all");
  const placeable = r.pending_suggestions - r.unsure;

  const approveAll = () =>
    approve.mutate(
      { params: { path: { project_id: projectId } }, body: {} },
      {
        onSuccess: (result) => {
          toast(t("catchup.approvedAll", { count: result.accepted }), "🗂️");
          burst(window.innerWidth / 2, window.innerHeight / 3);
          void invalidateProjects();
        },
      },
    );

  return (
    <section className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <h2 className="font-display text-2xl font-extrabold">✨ {t("catchup.resultsTitle")}</h2>
        {r.scan && (
          <div className="flex gap-2 text-sm">
            <Badge tone="info">
              ✉️ {r.scan.messages_imported} {t("catchup.statImported")}
            </Badge>
            <Badge tone="info">
              📎 {r.scan.files_imported} {t("catchup.statFiles")}
            </Badge>
          </div>
        )}
      </div>

      <AnimatePresence>
        {placeable > 0 && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, height: 0 }}
            className="flex flex-wrap items-center gap-3 rounded-2xl border-2 border-ink bg-accent-soft p-4"
          >
            <motion.span
              className="text-3xl"
              animate={{ scale: [1, 1.15, 1] }}
              transition={{ duration: 1.6, repeat: Infinity }}
            >
              🤖
            </motion.span>
            <p className="min-w-0 flex-1 font-medium">{t("suggestions.title")}</p>
            <Button disabled={approve.isPending} onClick={approveAll}>
              ✓ {t("catchup.approveAll", { count: placeable })}
            </Button>
            <Link to={`/projects/${projectId}?tab=inbox`} className="text-sm font-bold text-brand underline">
              {t("catchup.reviewOne")}
            </Link>
          </motion.div>
        )}
      </AnimatePresence>
      {approve.isError && <Alert>{message(approve.error)}</Alert>}
      {r.unsure > 0 && <p className="text-sm text-ink-soft">🤔 {t("catchup.unsure", { count: r.unsure })}</p>}

      <div className="grid gap-5 lg:grid-cols-2">
        <Card className="space-y-3">
          <h3 className="font-display text-xl font-extrabold text-success">{t("catchup.foundTitle")}</h3>
          {r.found.length === 0 && <p className="text-sm text-ink-soft">{t("catchup.foundEmpty")}</p>}
          <ul className="space-y-2">
            {r.found.map((item, i) => (
              <FoundRow key={item.requirement_id} item={item} index={i} />
            ))}
          </ul>
        </Card>
        <Card className="space-y-3 border-2 border-danger/30">
          <h3 className="font-display text-xl font-extrabold text-danger">📋 {t("catchup.missingTitle")}</h3>
          <p className="text-sm text-ink-soft">{r.missing.length ? t("catchup.missingHint") : t("catchup.missingEmpty")}</p>
          <ul className="space-y-2">
            {r.missing.map((item, i) => (
              <MissingRow key={item.requirement_id} projectId={projectId} item={item} index={i} />
            ))}
          </ul>
        </Card>
      </div>
      <Link to={`/projects/${projectId}`}>
        <Button variant="secondary">{t("catchup.backToProject")} ←</Button>
      </Link>
    </section>
  );
}

function StageIcon({ stage }: { stage: string }) {
  return <span className="text-lg">{isStageKey(stage) ? STAGE_ICON[stage] : "📌"}</span>;
}

function FoundRow({ item, index }: { item: ReportItem; index: number }) {
  const { t } = useTranslation();
  return (
    <motion.li
      initial={{ opacity: 0, x: 16 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: index * 0.04 }}
      className="flex items-center gap-2 rounded-xl bg-success-soft/60 px-3 py-2"
    >
      <StageIcon stage={item.stage} />
      <span className="min-w-0 flex-1 text-sm font-medium">{item.title}</span>
      {item.documents > 0 && <Badge tone="success">{t("catchup.docs", { count: item.documents })}</Badge>}
      {item.pending > 0 && <Badge tone="warning">{t("catchup.pending", { count: item.pending })}</Badge>}
    </motion.li>
  );
}

function MissingRow({ projectId, item, index }: { projectId: string; item: ReportItem; index: number }) {
  const { t } = useTranslation();
  const message = useErrorMessage();
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => setError(null), [item.documents]);

  const upload = async (files: FileList | null) => {
    if (!files?.length) return;
    setBusy(true);
    try {
      for (const file of Array.from(files)) await uploadFile(projectId, file, item.requirement_id, () => {});
    } catch (e) {
      setError(message(e));
    }
    setBusy(false);
    await invalidateProjects();
  };

  return (
    <motion.li
      initial={{ opacity: 0, x: 16 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: index * 0.04 }}
      className="space-y-1.5 rounded-xl bg-danger-soft/50 px-3 py-2"
    >
      <div className="flex items-center gap-2">
        <StageIcon stage={item.stage} />
        <span className="min-w-0 flex-1 text-sm font-medium">{item.title}</span>
        <Button size="sm" variant="secondary" disabled={busy} onClick={() => input.current?.click()}>
          📎 {t("catchup.upload")}
        </Button>
      </div>
      <div className="flex flex-wrap gap-1">
        {item.required_documents.map((doc) => (
          <span key={doc} className="rounded-full bg-surface px-2 py-0.5 text-xs">
            {doc}
          </span>
        ))}
      </div>
      {error && <Alert>{error}</Alert>}
      <input
        ref={input}
        type="file"
        multiple
        accept={UPLOAD_ACCEPT}
        className="hidden"
        onChange={(e) => void upload(e.target.files)}
      />
    </motion.li>
  );
}

/** On the project page while nothing has been gathered: the way into the import. */
export function CatchUpEntry({ projectId }: { projectId: string }) {
  const { t } = useTranslation();
  const report = $api.useQuery("get", REPORT, { params: { path: { project_id: projectId } } });
  if (report.data?.state !== "empty") return null;
  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
      <Link
        to={`/projects/${projectId}/import`}
        className="group flex flex-wrap items-center gap-4 rounded-2xl border-2 border-dashed border-ink bg-surface p-4 hover:bg-accent-soft"
      >
        <motion.span
          className="text-4xl"
          animate={{ rotate: [0, -8, 8, 0] }}
          transition={{ duration: 2.5, repeat: Infinity }}
        >
          🗂️
        </motion.span>
        <span className="min-w-0 flex-1">
          <span className="block font-display text-lg font-extrabold">{t("catchup.entryTitle")}</span>
          <span className="block text-sm text-ink-soft">{t("catchup.entryHint")}</span>
        </span>
        <span className="rounded-full bg-ink px-4 py-2 text-sm font-bold text-white transition group-hover:-translate-x-1">
          {t("catchup.entryCta")} ←
        </span>
      </Link>
    </motion.div>
  );
}
