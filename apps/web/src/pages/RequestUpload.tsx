import type { PublicRequest } from "@arba/api-client";
import { AnimatePresence, motion } from "motion/react";
import { useRef, useState, type DragEvent } from "react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router";
import { Logo } from "../components/Logo";
import { Alert, Button, Spinner, cx } from "../components/ui";
import { $api, api } from "../lib/api";
import { UPLOAD_ACCEPT, put } from "../lib/upload";

/** A professional's upload page, opened from a personal link: no account, no password. */
export function RequestUploadPage() {
  const { token = "" } = useParams();
  const { t } = useTranslation();
  const path = { params: { path: { token } } };
  const view = $api.useQuery("get", "/api/v1/public/requests/{token}", path, { retry: false });
  const [finished, setFinished] = useState(false);

  return (
    <div className="min-h-dvh bg-bg">
      <div className="mx-auto max-w-lg space-y-5 px-4 py-6">
        <Logo />
        {view.isPending && <Spinner label={t("app.loading")} />}
        {view.isError && (
          <div className="space-y-2 rounded-2xl border-2 border-ink bg-surface p-6 text-center">
            <div className="text-5xl">🔗</div>
            <h1 className="font-display text-2xl font-extrabold">{t("upload.invalid")}</h1>
            <p className="text-ink-soft">{t("upload.invalidHint")}</p>
          </div>
        )}
        {view.data &&
          (finished ? (
            <Thanks onMore={() => setFinished(false)} />
          ) : (
            <Asked token={token} request={view.data} onRefresh={() => void view.refetch()} onDone={() => setFinished(true)} />
          ))}
        <p className="pt-6 text-center text-xs text-ink-soft">{t("upload.footer")}</p>
      </div>
    </div>
  );
}

function Asked({
  token,
  request: r,
  onRefresh,
  onDone,
}: {
  token: string;
  request: PublicRequest;
  onRefresh: () => void;
  onDone: () => void;
}) {
  const { t } = useTranslation();
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const [current, setCurrent] = useState<{ name: string; progress: number } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [finishing, setFinishing] = useState(false);

  const upload = async (files: FileList | null) => {
    setError(null);
    for (const file of Array.from(files ?? [])) {
      setCurrent({ name: file.name, progress: 0 });
      try {
        const started = await api.fetchClient.POST("/api/v1/public/requests/{token}/uploads", {
          params: { path: { token } },
          body: { file_name: file.name, content_type: file.type || "application/octet-stream", size_bytes: file.size },
        });
        if (!started.data) throw new Error("start");
        await put(started.data.upload, file, (progress) => setCurrent({ name: file.name, progress }));
        const done = await api.fetchClient.POST("/api/v1/public/requests/{token}/uploads/{document_id}/complete", {
          params: { path: { token, document_id: started.data.document_id } },
        });
        if (!done.data) throw new Error("complete");
      } catch {
        setError(t("upload.failed"));
      }
    }
    setCurrent(null);
    onRefresh();
  };

  const finish = async () => {
    setFinishing(true);
    await api.fetchClient.POST("/api/v1/public/requests/{token}/done", { params: { path: { token } } });
    setFinishing(false);
    onDone();
  };

  return (
    <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="space-y-5">
      <div className="space-y-1">
        <h1 className="font-display text-3xl font-extrabold">{t("upload.hello", { name: r.contact_name })}</h1>
        <p className="text-ink-soft">{t("upload.asked", { who: r.requested_by })}</p>
      </div>

      <div className="space-y-3 rounded-2xl border-2 border-ink bg-surface p-4 shadow-[4px_4px_0_0_var(--color-ink)]">
        <div>
          <div className="font-display text-xl font-extrabold">🏠 {r.project_name}</div>
          {r.place && <div className="text-sm text-ink-soft">{r.place}</div>}
        </div>
        <div className="rounded-xl bg-accent-soft px-3 py-2">
          <div className="text-xs font-bold text-ink-soft">{t("upload.step")}</div>
          <div className="font-bold">{r.requirement_title}</div>
        </div>
        <div>
          <div className="mb-1.5 text-sm font-bold">📋 {t("upload.needed")}</div>
          <ul className="space-y-1">
            {r.documents.map((d, i) => (
              <motion.li
                key={d}
                initial={{ opacity: 0, x: 12 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.1 + i * 0.06 }}
                className="flex items-center gap-2 rounded-lg bg-bg px-3 py-2"
              >
                <span className="text-lg">📄</span>
                <span className="font-medium">{d}</span>
              </motion.li>
            ))}
          </ul>
        </div>
        {r.note && (
          <p className="rounded-lg bg-info-soft px-3 py-2 text-sm text-info">
            💬 <span className="font-bold">{t("upload.note")}:</span> {r.note}
          </p>
        )}
      </div>

      <motion.button
        type="button"
        disabled={current !== null}
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
        whileTap={{ scale: 0.97 }}
        animate={{ scale: over ? 1.03 : 1 }}
        className={cx(
          "relative flex w-full flex-col items-center gap-2 overflow-hidden rounded-3xl border-2 border-dashed p-8 text-center",
          over ? "border-accent bg-accent-soft" : "border-ink bg-surface",
        )}
      >
        {current ? (
          <>
            <motion.div
              className="absolute inset-y-0 start-0 bg-accent-soft"
              animate={{ width: `${Math.round(current.progress * 100)}%` }}
            />
            <span className="relative text-4xl">⏫</span>
            <span className="relative font-bold">{t("upload.uploading", { name: current.name })}</span>
          </>
        ) : (
          <>
            <motion.span className="text-5xl" animate={{ y: [0, -8, 0] }} transition={{ duration: 1.8, repeat: Infinity }}>
              📸
            </motion.span>
            <span className="font-display text-xl font-bold">{t("upload.drop")}</span>
            <span className="text-xs text-ink-soft">{t("upload.dropHint", { mb: r.max_upload_mb })}</span>
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
          void upload(e.target.files).then(() => (e.target.value = ""));
        }}
      />
      {error && <Alert>{error}</Alert>}

      <AnimatePresence>
        {r.files.length > 0 && (
          <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} className="space-y-2">
            <div className="text-sm font-bold">✅ {t("upload.uploaded")}</div>
            <ul className="space-y-1">
              {r.files.map((f) => (
                <motion.li
                  key={f.id}
                  layout
                  initial={{ opacity: 0, scale: 0.9 }}
                  animate={{ opacity: 1, scale: 1 }}
                  className="flex items-center gap-2 rounded-lg bg-success-soft px-3 py-2 text-sm"
                >
                  <span>📎</span>
                  <span className="min-w-0 flex-1 truncate">{f.file_name}</span>
                </motion.li>
              ))}
            </ul>
            <Button className="w-full" disabled={finishing || current !== null} onClick={() => void finish()}>
              ✓ {t("upload.done")}
            </Button>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

function Thanks({ onMore }: { onMore: () => void }) {
  const { t } = useTranslation();
  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.9 }}
      animate={{ opacity: 1, scale: 1 }}
      className="space-y-4 rounded-3xl border-2 border-ink bg-surface p-8 text-center shadow-[6px_6px_0_0_var(--color-accent)]"
    >
      <motion.div
        className="text-7xl"
        initial={{ rotate: -20, scale: 0 }}
        animate={{ rotate: 0, scale: 1 }}
        transition={{ type: "spring", stiffness: 260, damping: 12 }}
      >
        🎉
      </motion.div>
      <h1 className="font-display text-3xl font-extrabold">{t("upload.doneTitle")}</h1>
      <p className="text-ink-soft">{t("upload.doneText")}</p>
      <Button variant="secondary" onClick={onMore}>
        {t("upload.moreFiles")}
      </Button>
    </motion.div>
  );
}
