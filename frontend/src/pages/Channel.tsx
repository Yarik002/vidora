import { useEffect, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { PlaylistGrid } from "../components/PlaylistCard";
import { Avatar, Button, Chip, EmptyState, Modal, PageSpinner, Spinner, TextField } from "../components/ui";
import { VideoGrid } from "../components/VideoCard";
import { api, errorText } from "../lib/api";
import { useAuth } from "../lib/auth";
import { countText, fullDate, subscribersText } from "../lib/format";
import { useApi, useDocumentTitle, useInfiniteScroll, usePaged } from "../lib/hooks";
import type { ChannelDetail, Playlist, VideoCard } from "../lib/types";
import "./Channel.css";

type Tab = "videos" | "playlists" | "about";
const COLORS = ["#3ea6ff", "#ff4e45", "#2ba640", "#f9a825", "#ab47bc", "#ef6c00", "#26a69a", "#5c6bc0"];

function EditChannel({ channel, onClose, onSaved }: { channel: ChannelDetail; onClose: () => void; onSaved: (c: ChannelDetail) => void }) {
  const [form, setForm] = useState({ title: channel.title, description: channel.description, avatar_color: channel.avatar_color });
  const [error, setError] = useState<string | null>(null);
  const save = async () => {
    try {
      onSaved(await api<ChannelDetail>("/channels/me", { method: "PATCH", body: form }));
      onClose();
    } catch (err) {
      setError(errorText(err));
    }
  };
  return (
    <Modal
      title="Настройки канала"
      onClose={onClose}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Отмена
          </Button>
          <Button variant="accent" onClick={save} disabled={!form.title.trim()}>
            Сохранить
          </Button>
        </>
      }
    >
      <TextField label="Название" maxLength={100} value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
      <TextField
        label="Описание"
        multiline
        maxLength={5000}
        value={form.description}
        onChange={(e) => setForm({ ...form, description: e.target.value })}
      />
      <div className="field">
        <span className="field__label">Цвет аватара</span>
        <div className="row">
          {COLORS.map((c) => (
            <button
              key={c}
              type="button"
              className={`color-swatch ${form.avatar_color === c ? "color-swatch--active" : ""}`}
              style={{ backgroundColor: c }}
              aria-label={`Цвет ${c}`}
              onClick={() => setForm({ ...form, avatar_color: c })}
            />
          ))}
        </div>
      </div>
      {error && <p className="error-text">{error}</p>}
    </Modal>
  );
}

function ChannelVideos({ handle }: { handle: string }) {
  const [sort, setSort] = useState<"new" | "popular" | "old">("new");
  const list = usePaged<VideoCard>(`/channels/${handle}/videos?sort=${sort}`, 30);
  const sentinel = useInfiniteScroll(() => void list.loadMore(), list.hasMore && !list.loading);
  useEffect(() => {
    if (list.items.length === 0 && list.hasMore && !list.loading) void list.loadMore();
  }, [list]);
  return (
    <>
      <div className="row channel__sort">
        <Chip active={sort === "new"} onClick={() => setSort("new")}>
          Новые
        </Chip>
        <Chip active={sort === "popular"} onClick={() => setSort("popular")}>
          Популярные
        </Chip>
        <Chip active={sort === "old"} onClick={() => setSort("old")}>
          Старые
        </Chip>
      </div>
      {!list.loading && list.items.length === 0 && <EmptyState icon="film" title="На канале пока нет видео" />}
      <VideoGrid videos={list.items} />
      <div ref={sentinel} className="load-more">
        {list.loading && <Spinner />}
      </div>
    </>
  );
}

export function Channel() {
  const { handle = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const tab = (params.get("tab") as Tab) || "videos";
  const { user } = useAuth();
  const navigate = useNavigate();
  const { data: channel, setData, error, loading } = useApi<ChannelDetail>(`/channels/${handle}`);
  const playlists = useApi<Playlist[]>(tab === "playlists" ? `/channels/${handle}/playlists` : null);
  const [editing, setEditing] = useState(false);
  useDocumentTitle(channel?.title);

  if (loading && !channel) return <PageSpinner />;
  if (error || !channel) return <EmptyState icon="user" title="Канал не найден" />;

  const toggleSub = async () => {
    if (!user) return navigate(`/login?next=/channel/${handle}`);
    const r = await api<{ subscribed: boolean; subscribers_count: number }>(`/channels/${channel.id}/subscription`, {
      method: channel.is_subscribed ? "DELETE" : "PUT",
    });
    setData({ ...channel, is_subscribed: r.subscribed, subscribers_count: r.subscribers_count });
  };

  return (
    <div className="channel">
      <div className="channel__banner" style={{ background: `linear-gradient(120deg, ${channel.avatar_color}, #1f1f1f 75%)` }} />
      <header className="channel__header">
        <Avatar title={channel.title} color={channel.avatar_color} size={160} />
        <div className="channel__info">
          <h1>{channel.title}</h1>
          <p className="text-secondary">
            <strong className="channel__handle">@{channel.handle}</strong> • {subscribersText(channel.subscribers_count)} •{" "}
            {countText(channel.videos_count, "видео", "видео", "видео")}
          </p>
          {channel.description && (
            <button type="button" className="channel__desc text-secondary" onClick={() => setParams({ tab: "about" })}>
              {channel.description}
            </button>
          )}
          <div className="row channel__actions">
            {channel.is_owner ? (
              <>
                <Button onClick={() => setEditing(true)}>Настроить вид канала</Button>
                <Link to="/studio" className="btn btn--secondary btn--md">
                  Управление видео
                </Link>
              </>
            ) : channel.is_subscribed ? (
              <Button icon="bell" onClick={toggleSub}>
                Вы подписаны
              </Button>
            ) : (
              <Button variant="primary" onClick={toggleSub}>
                Подписаться
              </Button>
            )}
          </div>
        </div>
      </header>
      <nav className="channel__tabs" aria-label="Разделы канала">
        {(
          [
            ["videos", "Видео"],
            ["playlists", "Плейлисты"],
            ["about", "О канале"],
          ] as [Tab, string][]
        ).map(([key, label]) => (
          <button key={key} type="button" className={`channel__tab ${tab === key ? "is-active" : ""}`} onClick={() => setParams({ tab: key })}>
            {label}
          </button>
        ))}
      </nav>
      <div className="channel__content">
        {tab === "videos" && <ChannelVideos handle={handle} />}
        {tab === "playlists" &&
          (playlists.loading ? (
            <Spinner />
          ) : playlists.data && playlists.data.length > 0 ? (
            <PlaylistGrid playlists={playlists.data} />
          ) : (
            <EmptyState icon="playlist" title="Плейлистов пока нет" />
          ))}
        {tab === "about" && (
          <section className="channel__about">
            <h2>Описание</h2>
            <p>{channel.description || "Автор пока ничего не рассказал о канале."}</p>
            <h2>Статистика</h2>
            <p className="text-secondary">Дата регистрации: {fullDate(channel.created_at)}</p>
            <p className="text-secondary">{subscribersText(channel.subscribers_count)}</p>
          </section>
        )}
      </div>
      {editing && <EditChannel channel={channel} onClose={() => setEditing(false)} onSaved={setData} />}
    </div>
  );
}
