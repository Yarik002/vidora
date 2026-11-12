/** Search results, subscriptions feed, history, liked videos, playlists and the "You" hub. */
import { useEffect } from "react";
import { Link, Navigate, useSearchParams } from "react-router-dom";
import { PlaylistGrid } from "../components/PlaylistCard";
import { Avatar, Button, EmptyState, Spinner } from "../components/ui";
import { VideoCard, VideoGrid } from "../components/VideoCard";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { subscribersText } from "../lib/format";
import { useApi, useDocumentTitle, useInfiniteScroll, usePaged } from "../lib/hooks";
import type { ChannelBrief, Playlist, VideoCard as Card } from "../lib/types";
import "./pages.css";

function usePagedList(path: string | null, size = 24) {
  const list = usePaged<Card>(path, size);
  const sentinel = useInfiniteScroll(() => void list.loadMore(), list.hasMore && !list.loading);
  useEffect(() => {
    if (path && list.items.length === 0 && list.hasMore && !list.loading) void list.loadMore();
  }, [list, path]);
  return { list, sentinel };
}

function SignInPrompt({ title, text, next }: { title: string; text: string; next: string }) {
  return (
    <EmptyState icon="user" title={title}>
      <p>{text}</p>
      <Link to={`/login?next=${encodeURIComponent(next)}`} className="btn btn--outline-accent btn--md">
        Войти
      </Link>
    </EmptyState>
  );
}

export function SearchResults() {
  const [params] = useSearchParams();
  const q = (params.get("search_query") ?? "").trim();
  useDocumentTitle(q || "Поиск");
  const channels = useApi<ChannelBrief[]>(q ? `/search/channels?q=${encodeURIComponent(q)}` : null);
  const { list, sentinel } = usePagedList(q ? `/search?q=${encodeURIComponent(q)}` : null, 20);

  if (!q) return <EmptyState icon="search" title="Введите запрос в строке поиска" />;
  return (
    <div className="page-narrow results">
      {channels.data?.map((c) => (
        <Link key={c.id} to={`/channel/${c.handle}`} className="result-channel">
          <span className="result-channel__avatar">
            <Avatar title={c.title} color={c.avatar_color} size={136} />
          </span>
          <span className="result-channel__text">
            <span className="result-channel__title">{c.title}</span>
            <span className="text-secondary">
              @{c.handle} • {subscribersText(c.subscribers_count)}
            </span>
          </span>
        </Link>
      ))}
      {list.items.map((v) => (
        <VideoCard key={v.id} video={v} variant="list" />
      ))}
      {!list.loading && list.items.length === 0 && !list.hasMore && (
        <EmptyState icon="search" title="Ничего не найдено">
          <p>Попробуйте другие слова или проверьте опечатки.</p>
        </EmptyState>
      )}
      <div ref={sentinel} className="load-more">
        {list.loading && <Spinner />}
      </div>
    </div>
  );
}

export function SubscriptionsFeed() {
  useDocumentTitle("Подписки");
  const { user, loading } = useAuth();
  const subs = useApi<ChannelBrief[]>(user ? "/me/subscriptions" : null);
  const { list, sentinel } = usePagedList(user ? "/me/feed/subscriptions" : null);
  if (!loading && !user)
    return <SignInPrompt title="Не пропускайте новые видео" text="Войдите, чтобы видеть новинки каналов, на которые вы подписаны." next="/feed/subscriptions" />;
  return (
    <div className="page">
      <h1 className="page-title">Новые видео из подписок</h1>
      {subs.data && subs.data.length > 0 && (
        <div className="subs-strip">
          {subs.data.map((c) => (
            <Link key={c.id} to={`/channel/${c.handle}`} className="subs-strip__item" title={c.title}>
              <Avatar title={c.title} color={c.avatar_color} size={56} />
              <span>{c.title}</span>
            </Link>
          ))}
        </div>
      )}
      {!list.loading && list.items.length === 0 && !list.hasMore && (
        <EmptyState icon="subscriptions" title="Здесь появятся новые видео">
          <p>Подпишитесь на каналы, которые вам нравятся.</p>
        </EmptyState>
      )}
      <VideoGrid videos={list.items} />
      <div ref={sentinel} className="load-more">
        {list.loading && <Spinner />}
      </div>
    </div>
  );
}

function ListFeed({ title, path, emptyTitle, actions }: { title: string; path: string; emptyTitle: string; actions?: React.ReactNode }) {
  useDocumentTitle(title);
  const { user, loading } = useAuth();
  const { list, sentinel } = usePagedList(user ? path : null);
  if (!loading && !user) return <SignInPrompt title={title} text="Войдите, чтобы увидеть этот раздел." next={window.location.pathname} />;
  return (
    <div className="page-narrow">
      <div className="row">
        <h1 className="page-title spacer">{title}</h1>
        {actions}
      </div>
      {!list.loading && list.items.length === 0 && !list.hasMore && <EmptyState icon="film" title={emptyTitle} />}
      <div className="list-feed">
        {list.items.map((v) => (
          <VideoCard key={v.id} video={v} variant="list" />
        ))}
      </div>
      <div ref={sentinel} className="load-more">
        {list.loading && <Spinner />}
      </div>
    </div>
  );
}

export function History() {
  return (
    <ListFeed
      title="История просмотра"
      path="/me/history"
      emptyTitle="Вы пока ничего не смотрели"
      actions={
        <Button
          icon="trash"
          variant="ghost"
          onClick={async () => {
            if (!window.confirm("Очистить историю просмотра?")) return;
            await api("/me/history", { method: "DELETE" });
            window.location.reload();
          }}
        >
          Очистить историю
        </Button>
      }
    />
  );
}

export function Liked() {
  return <ListFeed title="Понравившиеся" path="/me/liked" emptyTitle="Поставьте лайк видео, и оно появится здесь" />;
}

export function MyPlaylists() {
  useDocumentTitle("Плейлисты");
  const { user, loading } = useAuth();
  const lists = useApi<Playlist[]>(user ? "/me/playlists" : null);
  if (!loading && !user) return <SignInPrompt title="Плейлисты" text="Войдите, чтобы создавать плейлисты." next="/feed/playlists" />;
  return (
    <div className="page">
      <h1 className="page-title">Плейлисты</h1>
      {lists.loading && <Spinner />}
      {lists.data?.length === 0 && (
        <EmptyState icon="playlist" title="Плейлистов пока нет">
          <p>Нажмите «Сохранить» под любым видео, чтобы создать плейлист.</p>
        </EmptyState>
      )}
      {lists.data && <PlaylistGrid playlists={lists.data} />}
    </div>
  );
}

export function You() {
  const { user, loading } = useAuth();
  if (!loading && !user) return <SignInPrompt title="Это ваш раздел" text="Войдите, чтобы видеть историю, плейлисты и свои видео." next="/feed/you" />;
  if (!user) return null;
  return <Navigate to={`/channel/${user.channel.handle}`} replace />;
}
