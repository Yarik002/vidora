import { Link, useNavigate, useParams } from "react-router-dom";
import { Icon } from "../components/Icon";
import { Button, EmptyState, IconButton, PageSpinner } from "../components/ui";
import { VideoCard } from "../components/VideoCard";
import { api } from "../lib/api";
import { timeAgo } from "../lib/format";
import { useApi, useDocumentTitle } from "../lib/hooks";
import type { PlaylistDetail, Visibility } from "../lib/types";
import "./pages.css";

const LABEL: Record<Visibility, string> = { public: "Открытый доступ", unlisted: "Доступ по ссылке", private: "Ограниченный доступ" };

export function PlaylistPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const { data: p, setData, error, loading } = useApi<PlaylistDetail>(`/playlists/${id}`);
  useDocumentTitle(p?.title);
  if (loading && !p) return <PageSpinner />;
  if (error || !p) return <EmptyState icon="playlist" title="Плейлист не найден или недоступен" />;

  const setVisibility = async (visibility: Visibility) => {
    setData(await api<PlaylistDetail>(`/playlists/${p.id}`, { method: "PATCH", body: { visibility } }));
  };
  const remove = async (videoId: string) => {
    await api(`/playlists/${p.id}/videos/${videoId}`, { method: "DELETE" });
    setData({ ...p, videos: p.videos.filter((v) => v.id !== videoId), items_count: p.items_count - 1 });
  };

  return (
    <div className="playlist-page">
      <aside className="playlist-page__hero">
        <div className="playlist-page__cover">
          {p.thumbnail_url ? <img src={p.thumbnail_url} alt="" /> : <Icon name="playlist" size={64} />}
        </div>
        <h1>{p.title}</h1>
        <Link to={`/channel/${p.channel.handle}`} className="playlist-page__owner">
          {p.channel.title}
        </Link>
        <p className="text-secondary">
          {LABEL[p.visibility]} • {p.items_count} видео • Обновлён {timeAgo(p.updated_at)}
        </p>
        {p.description && <p className="playlist-page__desc">{p.description}</p>}
        {p.videos[0] && (
          <Link to={`/watch/${p.videos[0].id}`} className="btn btn--primary btn--md">
            <Icon name="videos" size={20} /> Воспроизвести
          </Link>
        )}
        {p.is_owner && (
          <div className="playlist-page__owner-actions">
            <select className="field__input" value={p.visibility} onChange={(e) => void setVisibility(e.target.value as Visibility)} aria-label="Доступ">
              <option value="public">Открытый доступ</option>
              <option value="unlisted">Доступ по ссылке</option>
              <option value="private">Ограниченный доступ</option>
            </select>
            <Button
              variant="ghost"
              icon="trash"
              onClick={async () => {
                if (!window.confirm("Удалить плейлист?")) return;
                await api(`/playlists/${p.id}`, { method: "DELETE" });
                navigate("/feed/playlists");
              }}
            >
              Удалить
            </Button>
          </div>
        )}
      </aside>
      <section className="playlist-page__list">
        {p.videos.length === 0 && <EmptyState icon="film" title="В плейлисте нет доступных видео" />}
        {p.videos.map((v, i) => (
          <div key={v.id} className="playlist-row">
            <span className="playlist-row__index text-secondary">{i + 1}</span>
            <VideoCard video={v} variant="compact" />
            {p.is_owner && <IconButton icon="close" label="Убрать из плейлиста" onClick={() => void remove(v.id)} />}
          </div>
        ))}
      </section>
    </div>
  );
}
