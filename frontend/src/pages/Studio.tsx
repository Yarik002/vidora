import { useEffect, useState } from "react";
import { Link, Navigate } from "react-router-dom";
import { Icon } from "../components/Icon";
import { Button, EmptyState, IconButton, Modal, Spinner, TextField } from "../components/ui";
import { statusLabel } from "../components/VideoCard";
import { api, errorText } from "../lib/api";
import { useAuth } from "../lib/auth";
import { duration, fullDate } from "../lib/format";
import { useApi, useDocumentTitle, usePaged } from "../lib/hooks";
import type { AccessGrant, VideoCard, VideoDetail, Visibility } from "../lib/types";
import "./studio.css";

interface StudioVideo extends VideoCard {
  likes_count: number;
  comments_count: number;
  moderation_state: "active" | "hidden";
  processing_error: string | null;
}

const VIS: Record<Visibility, [string, "globe" | "link" | "lock"]> = {
  public: ["Открытый", "globe"],
  unlisted: ["По ссылке", "link"],
  private: ["Ограниченный", "lock"],
};

function EditDialog({ videoId, onClose, onSaved }: { videoId: string; onClose: () => void; onSaved: (v: VideoDetail) => void }) {
  const { data } = useApi<VideoDetail>(`/videos/${videoId}`);
  const [form, setForm] = useState<{ title: string; description: string; tags: string; visibility: Visibility } | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (data) setForm({ title: data.title, description: data.description, tags: data.tags.join(", "), visibility: data.visibility });
  }, [data]);
  const save = async () => {
    if (!form) return;
    try {
      const v = await api<VideoDetail>(`/videos/${videoId}`, {
        method: "PATCH",
        body: { ...form, tags: form.tags.split(",").map((t) => t.trim()).filter(Boolean) },
      });
      onSaved(v);
      onClose();
    } catch (err) {
      setError(errorText(err));
    }
  };
  return (
    <Modal
      title="Сведения о видео"
      onClose={onClose}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Отмена
          </Button>
          <Button variant="accent" onClick={save} disabled={!form?.title.trim()}>
            Сохранить
          </Button>
        </>
      }
    >
      {!form ? (
        <Spinner />
      ) : (
        <>
          <TextField label="Название" maxLength={100} value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
          <TextField label="Описание" multiline maxLength={5000} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
          <TextField label="Теги через запятую" value={form.tags} onChange={(e) => setForm({ ...form, tags: e.target.value })} />
          <label className="field">
            <span className="field__label">Доступ</span>
            <select className="field__input" value={form.visibility} onChange={(e) => setForm({ ...form, visibility: e.target.value as Visibility })}>
              <option value="public">Открытый доступ</option>
              <option value="unlisted">Доступ по ссылке</option>
              <option value="private">Ограниченный доступ</option>
            </select>
          </label>
        </>
      )}
      {error && <p className="error-text">{error}</p>}
    </Modal>
  );
}

function AccessDialog({ videoId, onClose }: { videoId: string; onClose: () => void }) {
  const grants = useApi<AccessGrant[]>(`/videos/${videoId}/access`);
  const [username, setUsername] = useState("");
  const [error, setError] = useState<string | null>(null);
  const add = async () => {
    setError(null);
    try {
      const g = await api<AccessGrant>(`/videos/${videoId}/access`, { method: "POST", body: { username: username.trim() } });
      grants.setData((all) => [...(all ?? []).filter((x) => x.user_id !== g.user_id), g]);
      setUsername("");
    } catch (err) {
      setError(errorText(err));
    }
  };
  const revoke = async (userId: string) => {
    await api(`/videos/${videoId}/access/${userId}`, { method: "DELETE" });
    grants.setData((all) => (all ?? []).filter((x) => x.user_id !== userId));
  };
  return (
    <Modal title="Кто может смотреть" onClose={onClose}>
      <p className="text-secondary">Ограниченное видео видите вы и пользователи из этого списка. Для остальных его не существует.</p>
      <div className="row access__add">
        <input
          className="field__input"
          placeholder="Имя пользователя"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && void add()}
        />
        <Button variant="accent" onClick={add} disabled={username.trim().length < 3}>
          Добавить
        </Button>
      </div>
      {error && <p className="error-text">{error}</p>}
      <ul className="access__list">
        {grants.data?.map((g) => (
          <li key={g.user_id} className="row">
            <Icon name="user" size={20} />
            <span className="spacer">@{g.username}</span>
            <IconButton icon="close" label={`Закрыть доступ для ${g.username}`} onClick={() => void revoke(g.user_id)} />
          </li>
        ))}
        {grants.data?.length === 0 && <li className="text-secondary">Пока никому не открыт доступ.</li>}
      </ul>
    </Modal>
  );
}

export function Studio() {
  useDocumentTitle("Мои видео");
  const { user, loading } = useAuth();
  const list = usePaged<StudioVideo>(user ? "/me/videos" : null, 50);
  const [editing, setEditing] = useState<string | null>(null);
  const [sharing, setSharing] = useState<string | null>(null);

  useEffect(() => {
    if (user && list.items.length === 0 && list.hasMore && !list.loading) void list.loadMore();
  }, [list, user]);
  // keep polling while something is still processing
  useEffect(() => {
    if (!list.items.some((v) => v.status !== "ready" && v.status !== "failed")) return;
    const t = window.setTimeout(async () => {
      const page = await api<{ items: StudioVideo[] }>(`/me/videos?limit=50`);
      list.setItems(page.items);
    }, 3000);
    return () => window.clearTimeout(t);
  }, [list]);

  if (!loading && !user) return <Navigate to="/login?next=/studio" replace />;

  const remove = async (v: StudioVideo) => {
    if (!window.confirm(`Удалить «${v.title}» навсегда? Файлы будут удалены из хранилища.`)) return;
    await api(`/videos/${v.id}`, { method: "DELETE" });
    list.setItems((items) => items.filter((x) => x.id !== v.id));
  };
  const setVisibility = async (v: StudioVideo, visibility: Visibility) => {
    await api(`/videos/${v.id}`, { method: "PATCH", body: { visibility } });
    list.setItems((items) => items.map((x) => (x.id === v.id ? { ...x, visibility } : x)));
  };

  return (
    <div className="page studio">
      <div className="row">
        <h1 className="page-title spacer">Контент на канале</h1>
        <Link to="/upload" className="btn btn--accent btn--md">
          <Icon name="upload" size={20} /> Добавить видео
        </Link>
      </div>
      {!list.loading && list.items.length === 0 && (
        <EmptyState icon="videos" title="У вас пока нет видео">
          <Link to="/upload" className="btn btn--secondary btn--md">
            Загрузить первое видео
          </Link>
        </EmptyState>
      )}
      {list.items.length > 0 && (
        <div className="studio-table" role="table" aria-label="Мои видео">
          <div className="studio-row studio-row--head" role="row">
            <span role="columnheader">Видео</span>
            <span role="columnheader">Доступ</span>
            <span role="columnheader">Статус</span>
            <span role="columnheader">Дата</span>
            <span role="columnheader">Просмотры</span>
            <span role="columnheader">Комм.</span>
            <span role="columnheader">Лайки</span>
            <span role="columnheader" />
          </div>
          {list.items.map((v) => (
            <div key={v.id} className="studio-row" role="row">
              <span className="studio-video" role="cell">
                <Link to={`/watch/${v.id}`} className="studio-video__thumb">
                  {v.thumbnail_url ? <img src={v.thumbnail_url} alt="" /> : <Icon name="film" />}
                  {v.duration_seconds != null && <span className="thumb__duration">{duration(v.duration_seconds)}</span>}
                </Link>
                <span className="studio-video__text">
                  <Link to={`/watch/${v.id}`} className="clamp-2">
                    {v.title}
                  </Link>
                  {v.moderation_state === "hidden" && <span className="badge badge--danger">Скрыто модератором</span>}
                </span>
              </span>
              <span role="cell">
                <label className="vis-select">
                  <Icon name={VIS[v.visibility][1]} size={18} />
                  <select value={v.visibility} onChange={(e) => void setVisibility(v, e.target.value as Visibility)} aria-label="Доступ">
                    {(Object.keys(VIS) as Visibility[]).map((k) => (
                      <option key={k} value={k}>
                        {VIS[k][0]}
                      </option>
                    ))}
                  </select>
                </label>
              </span>
              <span role="cell" className={v.status === "failed" ? "error-text" : v.status !== "ready" ? "text-secondary" : ""} title={v.processing_error ?? undefined}>
                {statusLabel(v.status)}
              </span>
              <span role="cell" className="text-secondary">
                {fullDate(v.published_at ?? v.created_at)}
              </span>
              <span role="cell">{v.views_count}</span>
              <span role="cell">{v.comments_count}</span>
              <span role="cell">{v.likes_count}</span>
              <span role="cell" className="studio-row__actions">
                <IconButton icon="edit" label="Изменить" onClick={() => setEditing(v.id)} />
                {v.visibility === "private" && <IconButton icon="users" label="Доступ" onClick={() => setSharing(v.id)} />}
                <IconButton icon="trash" label="Удалить" onClick={() => void remove(v)} />
              </span>
            </div>
          ))}
        </div>
      )}
      {list.loading && <Spinner />}
      {editing && (
        <EditDialog
          videoId={editing}
          onClose={() => setEditing(null)}
          onSaved={(d) => list.setItems((items) => items.map((x) => (x.id === d.id ? { ...x, title: d.title, visibility: d.visibility } : x)))}
        />
      )}
      {sharing && <AccessDialog videoId={sharing} onClose={() => setSharing(null)} />}
    </div>
  );
}
