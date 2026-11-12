import { useState } from "react";
import { api, errorText } from "../lib/api";
import { useApi } from "../lib/hooks";
import type { Playlist, Visibility } from "../lib/types";
import { Icon } from "./Icon";
import { Button, Modal, Spinner, TextField } from "./ui";

/** "Save to playlist": checkbox per own playlist + quick create. */
export function SaveDialog({ videoId, onClose }: { videoId: string; onClose: () => void }) {
  const lists = useApi<Playlist[]>(`/me/playlists?video_id=${videoId}`);
  const [creating, setCreating] = useState(false);
  const [title, setTitle] = useState("");
  const [visibility, setVisibility] = useState<Visibility>("public");
  const [error, setError] = useState<string | null>(null);

  const toggle = async (p: Playlist) => {
    setError(null);
    try {
      if (p.contains_video) await api(`/playlists/${p.id}/videos/${videoId}`, { method: "DELETE" });
      else await api(`/playlists/${p.id}/videos`, { method: "POST", body: { video_id: videoId } });
      lists.setData((all) => all?.map((x) => (x.id === p.id ? { ...x, contains_video: !p.contains_video } : x)) ?? null);
    } catch (err) {
      setError(errorText(err));
    }
  };

  const create = async () => {
    setError(null);
    try {
      const p = await api<Playlist>("/playlists", { method: "POST", body: { title, visibility } });
      await api(`/playlists/${p.id}/videos`, { method: "POST", body: { video_id: videoId } });
      lists.setData((all) => [{ ...p, contains_video: true }, ...(all ?? [])]);
      setCreating(false);
      setTitle("");
    } catch (err) {
      setError(errorText(err));
    }
  };

  return (
    <Modal title="Сохранить в..." onClose={onClose}>
      {lists.loading && <Spinner />}
      <div className="check-list">
        {lists.data?.map((p) => (
          <label key={p.id} className="check-list__item">
            <input type="checkbox" checked={Boolean(p.contains_video)} onChange={() => void toggle(p)} />
            <span className="spacer">{p.title}</span>
            <Icon name={p.visibility === "private" ? "lock" : p.visibility === "unlisted" ? "link" : "globe"} size={18} />
          </label>
        ))}
        {lists.data?.length === 0 && !creating && <p className="text-secondary">У вас пока нет плейлистов.</p>}
      </div>
      {creating ? (
        <div className="save-dialog__create">
          <TextField label="Название" maxLength={150} autoFocus value={title} onChange={(e) => setTitle(e.target.value)} />
          <label className="field">
            <span className="field__label">Доступ</span>
            <select className="field__input" value={visibility} onChange={(e) => setVisibility(e.target.value as Visibility)}>
              <option value="public">Открытый</option>
              <option value="unlisted">По ссылке</option>
              <option value="private">Ограниченный</option>
            </select>
          </label>
          <div className="row">
            <span className="spacer" />
            <Button variant="ghost" onClick={() => setCreating(false)}>
              Отмена
            </Button>
            <Button variant="accent" disabled={!title.trim()} onClick={create}>
              Создать
            </Button>
          </div>
        </div>
      ) : (
        <Button variant="ghost" icon="plus" onClick={() => setCreating(true)}>
          Создать плейлист
        </Button>
      )}
      {error && <p className="error-text">{error}</p>}
    </Modal>
  );
}
