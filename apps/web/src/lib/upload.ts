import type { DocumentOut } from "@arba/api-client";
import { api } from "./api";

/** Mirrors ALLOWED_EXTENSIONS in backend/app/modules/documents/service.py. */
export const UPLOAD_ACCEPT =
  ".pdf,.jpg,.jpeg,.png,.heic,.heif,.webp,.gif,.tif,.tiff,.doc,.docx,.xls,.xlsx,.csv,.txt,.dwg,.dxf,.zip";

/**
 * Three steps: ask the API for an upload URL, send the file straight to storage (with
 * progress), then confirm. The file never passes through the API in production.
 */
export async function uploadFile(
  projectId: string,
  file: File,
  requirementId: string | null,
  onProgress: (fraction: number) => void,
): Promise<DocumentOut> {
  const path = { project_id: projectId };
  const started = await api.fetchClient.POST("/api/v1/projects/{project_id}/documents", {
    params: { path },
    body: {
      file_name: file.name,
      content_type: file.type || "application/octet-stream",
      size_bytes: file.size,
      requirement_id: requirementId,
    },
  });
  if (!started.data) throw started.error;

  await put(started.data.upload, file, onProgress);

  const done = await api.fetchClient.POST(
    "/api/v1/projects/{project_id}/documents/{document_id}/complete",
    { params: { path: { ...path, document_id: started.data.document_id } } },
  );
  if (!done.data) throw done.error;
  return done.data;
}

// XMLHttpRequest rather than fetch: fetch can't report upload progress.
function put(
  target: { url: string; method: string; headers: Record<string, string> },
  file: File,
  onProgress: (fraction: number) => void,
) {
  return new Promise<void>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open(target.method, target.url);
    for (const [name, value] of Object.entries(target.headers)) xhr.setRequestHeader(name, value);
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(e.loaded / e.total);
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) return resolve();
      try {
        reject(JSON.parse(xhr.responseText));
      } catch {
        reject(new Error(`upload failed: ${xhr.status}`));
      }
    };
    xhr.onerror = () => reject(new Error("upload failed"));
    xhr.send(file);
  });
}

export function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function fileIcon(name: string, contentType: string) {
  const ext = name.split(".").pop()?.toLowerCase() ?? "";
  if (contentType.startsWith("image/")) return "🖼️";
  if (ext === "pdf") return "📄";
  if (["xls", "xlsx", "csv"].includes(ext)) return "📊";
  if (["doc", "docx", "txt"].includes(ext)) return "📝";
  if (["dwg", "dxf"].includes(ext)) return "📐";
  if (ext === "zip") return "🗜️";
  return "📎";
}

const dateTime = new Intl.DateTimeFormat("he-IL", { dateStyle: "short", timeStyle: "short" });
export const formatDateTime = (iso: string) => dateTime.format(new Date(iso));
