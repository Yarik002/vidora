import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Comments } from "../components/Comments";
import { Icon } from "../components/Icon";
import { Player } from "../components/Player";
import { toastError } from "../components/Toast";
import { ReportDialog } from "../components/ReportDialog";
import { SaveDialog } from "../components/SaveDialog";
import { Avatar, Button, EmptyState, Menu, PageSpinner, Spinner } from "../components/ui";
import { statusLabel, VideoCard } from "../components/VideoCard";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { compactNumber, fullDate, subscribersText, timeAgo, viewsText } from "../lib/format";
import { useApi, useDocumentTitle } from "../lib/hooks";
import type { Page, VideoCard as Card, VideoDetail } from "../lib/types";
import "./Watch.css";

function SubscribeButton({ video, onChange }: { video: VideoDetail; onChange: (v: Partial<VideoDetail>) => void }) {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  if (video.is_owner) {
    return (
      <Link to="/studio" className="btn btn--secondary btn--md">
        Управлять видео
      </Link>
    );
  }
  const toggle = async () => {
    if (!user) return navigate(`/login?next=/watch/${video.id}`);
    setBusy(true);
    try {
      const r = await api<{ subscribed: boolean; subscribers_count: number }>(`/channels/${video.channel.id}/subscription`, {
        method: video.is_subscribed ? "DELETE" : "PUT",
      });
      onChange({ is_subscribed: r.subscribed, channel: { ...video.channel, subscribers_count: r.subscribers_count } });
    } catch (err) {
      toastError(err);
    } finally {
      setBusy(false);
    }
  };
  return video.is_subscribed ? (
    <Button variant="secondary" icon="bell" onClick={toggle} disabled={busy}>
      Вы подписаны
    </Button>
  ) : (
    <Button variant="primary" onClick={toggle} disabled={busy}>
      Подписаться
    </Button>
  );
}

function Description({ video }: { video: VideoDetail }) {
  const [open, setOpen] = useState(false);
  return (
    <div className={`description ${open ? "" : "description--collapsed"}`} onClick={() => !open && setOpen(true)}>
      <div className="description__meta">
        <span>{open ? `${video.views_count.toLocaleString("ru-RU")} просмотров` : viewsText(video.views_count)}</span>
        <span>{open ? fullDate(video.published_at) : timeAgo(video.published_at)}</span>
        {video.tags.map((t) => (
          <Link key={t} to={`/results?search_query=${encodeURIComponent(t)}`} className="description__tag" onClick={(e) => e.stopPropagation()}>
            #{t}
          </Link>
        ))}
      </div>
      <p className="description__text">{video.description || "Нет описания."}</p>
      <button type="button" className="description__toggle" onClick={(e) => (e.stopPropagation(), setOpen(!open))}>
        {open ? "Свернуть" : "ещё"}
      </button>
    </div>
  );
}

function Actions({ video, onChange }: { video: VideoDetail; onChange: (v: Partial<VideoDetail>) => void }) {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [dialog, setDialog] = useState<"save" | "report" | null>(null);
  const [copied, setCopied] = useState(false);

  const react = async (value: 1 | -1) => {
    if (!user) return navigate(`/login?next=/watch/${video.id}`);
    const next = video.my_reaction === value ? 0 : value;
    // optimistic update, rolled back on error
    const prev = { likes_count: video.likes_count, dislikes_count: video.dislikes_count, my_reaction: video.my_reaction };
    onChange({
      my_reaction: next,
      likes_count: video.likes_count + (next === 1 ? 1 : 0) - (video.my_reaction === 1 ? 1 : 0),
      dislikes_count: video.dislikes_count + (next === -1 ? 1 : 0) - (video.my_reaction === -1 ? 1 : 0),
    });
    try {
      onChange(await api(`/videos/${video.id}/reaction`, { method: "PUT", body: { value: next } }));
    } catch (err) {
      onChange(prev);
      toastError(err);
    }
  };

  const share = async () => {
    const url = `${window.location.origin}/watch/${video.id}`;
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      window.prompt("Ссылка на видео", url);
    }
  };

  return (
    <div className="watch__actions">
      <div className="like-pill">
        <button
          type="button"
          className={`like-pill__btn ${video.my_reaction === 1 ? "is-active" : ""}`}
          onClick={() => react(1)}
          aria-pressed={video.my_reaction === 1}
          title="Нравится"
        >
          <Icon name="like" />
          <span>{compactNumber(video.likes_count)}</span>
        </button>
        <span className="like-pill__divider" />
        <button
          type="button"
          className={`like-pill__btn ${video.my_reaction === -1 ? "is-active" : ""}`}
          onClick={() => react(-1)}
          aria-pressed={video.my_reaction === -1}
          title="Не нравится"
        >
          <Icon name="dislike" />
        </button>
      </div>
      <Button icon="share" onClick={share}>
        {copied ? "Скопировано" : "Поделиться"}
      </Button>
      {user && (
        <Button icon="save" onClick={() => setDialog("save")}>
          Сохранить
        </Button>
      )}
      {user && !video.is_owner && (
        <Menu
          items={[{ icon: "flag", label: "Пожаловаться", onClick: () => setDialog("report") }]}
          trigger={(props) => <Button icon="more" aria-label="Ещё" {...props} />}
        />
      )}
      {dialog === "save" && <SaveDialog videoId={video.id} onClose={() => setDialog(null)} />}
      {dialog === "report" && <ReportDialog target={{ video_id: video.id }} onClose={() => setDialog(null)} />}
    </div>
  );
}

export function Watch() {
  const { id = "" } = useParams();
  const { data: video, setData, error, loading } = useApi<VideoDetail>(`/videos/${id}`);
  const related = useApi<Page<Card>>(`/videos/${id}/related`);
  useDocumentTitle(video?.title);

  // Poll while the owner's video is still processing.
  useEffect(() => {
    if (!video || video.status === "ready" || video.status === "failed") return;
    const t = window.setTimeout(async () => {
      try {
        const fresh = await api<VideoDetail>(`/videos/${id}`);
        // the user may have navigated to another video meanwhile
        setData((current) => (current && current.id === fresh.id ? fresh : current));
      } catch {
        /* keep the old state */
      }
    }, 3000);
    return () => window.clearTimeout(t);
  }, [video, id, setData]);

  if (loading && !video) return <PageSpinner />;
  if (error || !video) {
    return (
      <EmptyState icon="lock" title="Видео недоступно">
        <p>{error ?? "Возможно, его удалили или автор ограничил доступ."}</p>
        <Link to="/" className="btn btn--secondary btn--md">
          На главную
        </Link>
      </EmptyState>
    );
  }

  const update = (patch: Partial<VideoDetail>) => setData((v) => (v ? { ...v, ...patch } : v));

  return (
    <div className="watch">
      <div className="watch__primary">
        {video.moderation_state === "hidden" && (
          <div className="banner banner--danger">
            <Icon name="eyeOff" /> Видео скрыто модератором. Его видите только вы и модераторы.
          </div>
        )}
        {video.status === "ready" ? (
          <Player video={video} onFirstPlay={() => void api(`/videos/${video.id}/view`, { method: "POST" }).catch(() => undefined)} />
        ) : (
          <div className="player player--pending">
            {video.status === "failed" ? <Icon name="close" size={48} /> : <Spinner size={48} />}
            <p>{statusLabel(video.status)}</p>
            {video.processing_error && <p className="text-secondary">{video.processing_error}</p>}
          </div>
        )}
        <h1 className="watch__title">{video.title}</h1>
        <div className="watch__bar">
          <div className="watch__channel">
            <Avatar title={video.channel.title} color={video.channel.avatar_color} size={40} to={`/channel/${video.channel.handle}`} />
            <div className="watch__channel-text">
              <Link to={`/channel/${video.channel.handle}`} className="watch__channel-name">
                {video.channel.title}
              </Link>
              <span className="text-secondary">{subscribersText(video.channel.subscribers_count)}</span>
            </div>
            <SubscribeButton video={video} onChange={update} />
          </div>
          <Actions video={video} onChange={update} />
        </div>
        {video.visibility !== "public" && (
          <div className="banner">
            <Icon name={video.visibility === "private" ? "lock" : "link"} />
            {video.visibility === "private" ? "Видео с ограниченным доступом" : "Видео доступно только по ссылке"}
          </div>
        )}
        <Description video={video} />
        <Comments videoId={video.id} count={video.comments_count} />
      </div>
      <aside className="watch__secondary" aria-label="Рекомендации">
        {related.data?.items.map((v) => <VideoCard key={v.id} video={v} variant="compact" />)}
        {related.error && <p className="text-secondary">{related.error}</p>}
      </aside>
    </div>
  );
}
