import { useEffect, useRef, useState, type DragEvent } from "react";
import { Link, Navigate } from "react-router-dom";
import { Icon } from "../components/Icon";
import { Button, ProgressBar, TextField } from "../components/ui";
import { statusLabel } from "../components/VideoCard";
import { api, errorText } from "../lib/api";
import { useAuth } from "../lib/auth";
import { fileSize } from "../lib/format";
import { useDocumentTitle } from "../lib/hooks";
import { startUpload, type UploadHandle } from "../lib/upload";
import type { VideoStatusOut, Visibility } from "../lib/types";
import "./pages.css";

type Phase = "select" | "uploading" | "processing" | "ready" | "failed";

const VISIBILITY: [Visibility, string, string][] = [
  ["public", "Открытый доступ", "Видео увидят все, оно появится в ленте и поиске"],
  ["unlisted", "Доступ по ссылке", "Смотреть могут все, у кого есть ссылка"],
  ["private", "Ограниченный доступ", "Только вы и те, кому вы откроете доступ"],
];

export function Upload() {
  useDocumentTitle("Загрузка видео");
  const { user, loading } = useAuth();
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [phase, setPhase] = useState<Phase>("select");
  const [progress, setProgress] = useState(0);
  const [speed, setSpeed] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [handle, setHandle] = useState<UploadHandle | null>(null);
  const [status, setStatus] = useState<VideoStatusOut | null>(null);
  const [form, setForm] = useState({ title: "", description: "", tags: "", visibility: "public" as Visibility });
  const [saved, setSaved] = useState<"no" | "saving" | "yes">("no");
  const [dragOver, setDragOver] = useState(false);

  // Poll processing status after the upload is complete.
  useEffect(() => {
    if (phase !== "processing" || !handle) return;
    const t = window.setInterval(async () => {
      try {
        const s = await api<VideoStatusOut>(`/videos/${handle.videoId}/status`);
        setStatus(s);
        if (s.status === "ready") setPhase("ready");
        if (s.status === "failed") setPhase("failed");
      } catch {
        /* transient */
      }
    }, 2000);
    return () => window.clearInterval(t);
  }, [phase, handle]);

  // Warn before closing the tab in the middle of an upload.
  useEffect(() => {
    if (phase !== "uploading") return;
    const onBeforeUnload = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [phase]);

  if (!loading && !user) return <Navigate to="/login?next=/upload" replace />;

  const begin = async (f: File) => {
    setError(null);
    if (!f.type.startsWith("video/") && !/\.(mp4|mov|mkv|webm|avi|m4v)$/i.test(f.name)) {
      setError("Похоже, это не видеофайл. Сервер всё равно проверит содержимое.");
    }
    setFile(f);
    const title = f.name.replace(/\.[^.]+$/, "").slice(0, 100) || "Новое видео";
    setForm((s) => ({ ...s, title }));
    setPhase("uploading");
    const started = Date.now();
    try {
      // Created as a private draft: nobody sees it until the details are saved.
      const h = await startUpload(f, { title, visibility: "private" }, ({ loaded, total }) => {
        setProgress((loaded / total) * 100);
        const secs = (Date.now() - started) / 1000;
        if (secs > 1) setSpeed(`${fileSize(loaded / secs)}/с`);
      });
      setHandle(h);
      const result = await h.done;
      setStatus(result);
      setProgress(100);
      setPhase("processing");
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") return;
      setError(err instanceof Error && !("code" in err) ? err.message : errorText(err));
      setPhase("failed");
    }
  };

  const save = async () => {
    if (!handle) return;
    setSaved("saving");
    setError(null);
    try {
      await api(`/videos/${handle.videoId}`, {
        method: "PATCH",
        body: {
          title: form.title.trim() || "Без названия",
          description: form.description,
          visibility: form.visibility,
          tags: form.tags.split(",").map((t) => t.trim()).filter(Boolean),
        },
      });
      setSaved("yes");
    } catch (err) {
      setError(errorText(err));
      setSaved("no");
    }
  };

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const f = e.dataTransfer.files[0];
    if (f) void begin(f);
  };

  if (phase === "select") {
    return (
      <div className="page-narrow">
        <h1 className="page-title">Загрузка видео</h1>
        <div
          className={`dropzone ${dragOver ? "dropzone--over" : ""}`}
          onDragOver={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={onDrop}
        >
          <span className="dropzone__icon">
            <Icon name="upload" size={56} />
          </span>
          <p className="dropzone__title">Перетащите файл сюда</p>
          <p className="text-secondary">Пока вы заполняете описание, видео загружается и обрабатывается</p>
          <Button variant="primary" onClick={() => inputRef.current?.click()}>
            Выбрать файл
          </Button>
          <input
            ref={inputRef}
            type="file"
            accept="video/*"
            hidden
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) void begin(f);
            }}
          />
          <p className="text-secondary dropzone__hint">MP4, MOV, WebM, MKV и другие форматы, до 1 ГБ</p>
          {error && <p className="error-text">{error}</p>}
        </div>
      </div>
    );
  }

  return (
    <div className="page-narrow upload">
      <h1 className="page-title">{form.title || "Новое видео"}</h1>
      <div className="upload__layout">
        <div className="upload__form">
          <h2 className="upload__section">Детали</h2>
          <TextField
            label="Название (обязательно)"
            maxLength={100}
            value={form.title}
            hint={`${form.title.length}/100`}
            onChange={(e) => setForm({ ...form, title: e.target.value })}
          />
          <TextField
            label="Описание"
            multiline
            maxLength={5000}
            value={form.description}
            placeholder="Расскажите зрителям о видео"
            onChange={(e) => setForm({ ...form, description: e.target.value })}
          />
          <TextField
            label="Теги через запятую"
            value={form.tags}
            placeholder="музыка, обзор, природа"
            onChange={(e) => setForm({ ...form, tags: e.target.value })}
          />
          <h2 className="upload__section">Параметры доступа</h2>
          <fieldset className="radio-list">
            <legend className="visually-hidden">Доступ</legend>
            {VISIBILITY.map(([value, label, hint]) => (
              <label key={value} className="radio-list__item radio-list__item--rich">
                <input
                  type="radio"
                  name="visibility"
                  checked={form.visibility === value}
                  onChange={() => setForm({ ...form, visibility: value })}
                />
                <span>
                  <strong>{label}</strong>
                  <span className="text-secondary">{hint}</span>
                </span>
              </label>
            ))}
          </fieldset>
          {form.visibility === "private" && (
            <p className="text-secondary">Кому открыть доступ, можно указать в разделе «Мои видео» после загрузки.</p>
          )}
          {error && <p className="error-text" role="alert">{error}</p>}
        </div>

        <aside className="upload__side">
          <div className="upload__preview">
            {status?.thumbnail_url ? <img src={status.thumbnail_url} alt="" /> : <Icon name="film" size={48} />}
          </div>
          <dl className="upload__info">
            <dt>Файл</dt>
            <dd>
              {file?.name} ({file && fileSize(file.size)})
            </dd>
            {handle && (
              <>
                <dt>Ссылка на видео</dt>
                <dd>
                  <Link to={`/watch/${handle.videoId}`} className="link-accent">
                    /watch/{handle.videoId.slice(0, 8)}…
                  </Link>
                </dd>
              </>
            )}
          </dl>
        </aside>
      </div>

      <footer className="upload__footer">
        <div className="upload__status">
          {phase === "uploading" && (
            <>
              <span>
                Загрузка {Math.floor(progress)}% {speed && <span className="text-secondary">• {speed}</span>}
              </span>
              <ProgressBar value={progress} />
            </>
          )}
          {phase === "processing" && (
            <>
              <span>{status ? statusLabel(status.status) : "Обработка"}… видео перекодируется в 720p и 360p</span>
              <ProgressBar value={100} />
            </>
          )}
          {phase === "ready" && (
            <span className="upload__ok">
              <Icon name="check" /> Обработка завершена
            </span>
          )}
          {phase === "failed" && (
            <span className="error-text">{status?.processing_error ?? error ?? "Не удалось загрузить видео"}</span>
          )}
        </div>
        {phase === "uploading" && handle && (
          <Button variant="ghost" onClick={() => (handle.cancel(), setPhase("select"), setProgress(0))}>
            Отменить
          </Button>
        )}
        {saved === "yes" && handle && phase === "ready" ? (
          <Link to={`/watch/${handle.videoId}`} className="btn btn--accent btn--md">
            Смотреть
          </Link>
        ) : (
          <Button variant="accent" disabled={!handle || saved === "saving" || phase === "failed"} onClick={save}>
            {saved === "yes" ? "Сохранено" : form.visibility === "private" ? "Сохранить" : "Опубликовать"}
          </Button>
        )}
      </footer>
    </div>
  );
}
