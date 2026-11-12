import { useEffect, useState } from "react";
import { Chip, EmptyState, Spinner } from "../components/ui";
import { VideoGrid, VideoGridSkeleton } from "../components/VideoCard";
import { useApi, useDocumentTitle, useInfiniteScroll, usePaged } from "../lib/hooks";
import type { VideoCard } from "../lib/types";
import "./pages.css";

export function Home() {
  useDocumentTitle(undefined);
  const [tag, setTag] = useState<string | null>(null);
  const tags = useApi<string[]>("/videos/tags");
  const feed = usePaged<VideoCard>(tag ? `/videos?tag=${encodeURIComponent(tag)}` : "/videos");
  const sentinel = useInfiniteScroll(() => void feed.loadMore(), feed.hasMore && !feed.loading);

  // first page
  useEffect(() => {
    if (feed.items.length === 0 && feed.hasMore && !feed.loading) void feed.loadMore();
  }, [feed]);

  return (
    <div className="page home">
      <div className="chips-bar" role="toolbar" aria-label="Фильтры">
        <Chip active={tag === null} onClick={() => setTag(null)}>
          Все
        </Chip>
        {tags.data?.map((t) => (
          <Chip key={t} active={tag === t} onClick={() => setTag(t)}>
            {t}
          </Chip>
        ))}
      </div>

      {feed.items.length === 0 && feed.loading && <VideoGridSkeleton />}
      {feed.items.length === 0 && !feed.loading && !feed.hasMore && (
        <EmptyState icon="film" title="Пока нет видео">
          <p>Загрузите первое видео кнопкой «Создать» в шапке.</p>
        </EmptyState>
      )}
      {feed.error && <p className="error-text">{feed.error}</p>}
      <VideoGrid videos={feed.items} />
      <div ref={sentinel} className="load-more">
        {feed.loading && feed.items.length > 0 && <Spinner />}
      </div>
    </div>
  );
}
