import { api } from "./api";
import type { UploadOut, VideoStatusOut, Visibility } from "./types";

export interface UploadProgress {
  loaded: number;
  total: number;
}

export interface UploadHandle {
  videoId: string;
  done: Promise<VideoStatusOut>;
  cancel: () => void;
}

const PARALLEL_PARTS = 3;

/** PUT one part straight to storage (same origin /storage/... -> MinIO). Returns the ETag. */
function putPart(
  url: string,
  blob: Blob,
  onProgress: (loaded: number) => void,
  register: (xhr: XMLHttpRequest) => void,
): Promise<string> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    register(xhr);
    xhr.open("PUT", url);
    xhr.upload.onprogress = (e) => onProgress(e.loaded);
    xhr.onload = () => {
      const etag = xhr.getResponseHeader("ETag");
      if (xhr.status >= 200 && xhr.status < 300 && etag) resolve(etag);
      else reject(new Error(`Хранилище отклонило часть файла (${xhr.status})`));
    };
    xhr.onerror = () => reject(new Error("Обрыв связи при загрузке"));
    xhr.onabort = () => reject(new DOMException("aborted", "AbortError"));
    xhr.send(blob);
  });
}

/**
 * Starts a direct-to-storage multipart upload. The video is created as a private draft;
 * the user publishes it (changes visibility) when the details form is saved.
 */
export async function startUpload(
  file: File,
  meta: { title: string; visibility: Visibility },
  onProgress: (p: UploadProgress) => void,
): Promise<UploadHandle> {
  const upload = await api<UploadOut>("/uploads", {
    method: "POST",
    body: {
      filename: file.name,
      size_bytes: file.size,
      content_type: file.type || "application/octet-stream",
      title: meta.title,
      visibility: meta.visibility,
    },
  });

  const xhrs = new Set<XMLHttpRequest>();
  let cancelled = false;
  const loadedPerPart = new Map<number, number>();
  const report = () => {
    let loaded = 0;
    loadedPerPart.forEach((v) => (loaded += v));
    onProgress({ loaded, total: file.size });
  };

  const done = (async () => {
    const etags: { part_number: number; etag: string }[] = [];
    const queue = [...upload.parts];
    const worker = async () => {
      while (queue.length && !cancelled) {
        const part = queue.shift()!;
        const start = (part.part_number - 1) * upload.part_size;
        const blob = file.slice(start, Math.min(start + upload.part_size, file.size));
        let attempt = 0;
        for (;;) {
          try {
            const etag = await putPart(
              part.url,
              blob,
              (loaded) => {
                loadedPerPart.set(part.part_number, loaded);
                report();
              },
              (xhr) => xhrs.add(xhr),
            );
            etags.push({ part_number: part.part_number, etag });
            loadedPerPart.set(part.part_number, blob.size);
            report();
            break;
          } catch (err) {
            if (cancelled) throw err;
            if (++attempt >= 3) {
              // give up on the whole upload: stop other parts and abort it on the server
              cancelled = true;
              xhrs.forEach((x) => x.abort());
              api(`/uploads/${upload.upload_id}`, { method: "DELETE" }).catch(() => undefined);
              throw err;
            }
            await new Promise((r) => setTimeout(r, 1000 * attempt)); // retry a flaky part
          }
        }
      }
    };
    await Promise.all(Array.from({ length: Math.min(PARALLEL_PARTS, upload.parts.length) }, worker));
    if (cancelled) throw new DOMException("aborted", "AbortError");
    return api<VideoStatusOut>(`/uploads/${upload.upload_id}/complete`, {
      method: "POST",
      body: { parts: etags },
    });
  })();

  return {
    videoId: upload.video_id,
    done,
    cancel: () => {
      cancelled = true;
      xhrs.forEach((x) => x.abort());
      api(`/uploads/${upload.upload_id}`, { method: "DELETE" }).catch(() => undefined);
    },
  };
}
