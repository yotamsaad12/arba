import { useCallback, useState } from "react";
import { useTranslation } from "react-i18next";
import { useCelebrate } from "../components/Celebrations";
import { invalidateProjects } from "../lib/api";
import { uploadFile } from "../lib/upload";
import { useErrorMessage } from "../lib/useErrorMessage";

export interface UploadItem {
  id: string;
  name: string;
  progress: number;
  error?: string;
}

/** Uploads files in parallel, tracking progress per file, then refreshes project data. */
export function useUploads(projectId: string) {
  const { t } = useTranslation();
  const message = useErrorMessage();
  const celebrate = useCelebrate();
  const [items, setItems] = useState<UploadItem[]>([]);

  const update = (id: string, patch: Partial<UploadItem>) =>
    setItems((list) => list.map((item) => (item.id === id ? { ...item, ...patch } : item)));

  const upload = useCallback(
    async (files: Iterable<File>, requirementId: string | null = null) => {
      const list = [...files];
      if (!list.length) return;
      let uploaded = 0;
      await Promise.all(
        list.map(async (file) => {
          const id = crypto.randomUUID();
          setItems((current) => [...current, { id, name: file.name, progress: 0 }]);
          try {
            await uploadFile(projectId, file, requirementId, (progress) => update(id, { progress }));
            uploaded++;
            update(id, { progress: 1 });
            window.setTimeout(() => setItems((current) => current.filter((i) => i.id !== id)), 900);
          } catch (error) {
            update(id, { error: message(error) });
            window.setTimeout(() => setItems((current) => current.filter((i) => i.id !== id)), 6000);
          }
        }),
      );
      await invalidateProjects();
      if (uploaded) celebrate.toast(t("documents.uploadedToast", { count: uploaded }), "📎");
    },
    [projectId, message, celebrate, t],
  );

  return { upload, items, busy: items.some((i) => !i.error && i.progress < 1) };
}
