import { Link } from "react-router-dom";
import { duration, timeAgo, viewsText } from "../lib/format";
import type { VideoCard as Video } from "../lib/types";
import { Icon } from "./Icon";
import { Avatar } from "./ui";
import "./VideoCard.css";

type Variant = "grid" | "compact" | "list";

export function Thumbnail({ video, size }: { video: Video; size?: "sm" }) {
  return (
    <Link to={`/watch/${video.id}`} className={`thumb ${size === "sm" ? "thumb--sm" : ""}`} tabIndex={-1}>
      {video.thumbnail_url ? (
        <img src={video.thumbnail_url} alt="" loading="lazy" />
      ) : (
        <span className="thumb__placeholder">
          <Icon name="film" size={40} />
          {video.status !== "ready" && <span>{statusLabel(video.status)}</span>}
        </span>
      )}
      {video.duration_seconds != null && <span className="thumb__duration">{duration(video.duration_seconds)}</span>}
    </Link>
  );
}

export function statusLabel(status: Video["status"]): string {
  return {
    uploading: "Загружается",
    uploaded: "В очереди",
    processing: "Обрабатывается",
    ready: "Готово",
    failed: "Ошибка обработки",
  }[status];
}

export function VideoCard({ video, variant = "grid", description }: { video: Video; variant?: Variant; description?: string }) {
  const meta = `${viewsText(video.views_count)} • ${timeAgo(video.published_at ?? video.created_at)}`;
  const channelLink = `/channel/${video.channel.handle}`;

  if (variant === "grid") {
    return (
      <article className="vcard vcard--grid">
        <Thumbnail video={video} />
        <div className="vcard__body">
          <Avatar title={video.channel.title} color={video.channel.avatar_color} to={channelLink} />
          <div className="vcard__text">
            <Link to={`/watch/${video.id}`} className="vcard__title clamp-2" title={video.title}>
              {video.title}
            </Link>
            <Link to={channelLink} className="vcard__meta vcard__channel">
              {video.channel.title}
            </Link>
            <div className="vcard__meta">{meta}</div>
          </div>
        </div>
      </article>
    );
  }

  return (
    <article className={`vcard vcard--${variant}`}>
      <Thumbnail video={video} size={variant === "compact" ? "sm" : undefined} />
      <div className="vcard__text">
        <Link to={`/watch/${video.id}`} className="vcard__title clamp-2" title={video.title}>
          {video.title}
        </Link>
        {variant === "list" && <div className="vcard__meta">{meta}</div>}
        <Link to={channelLink} className="vcard__meta vcard__channel row">
          {variant === "list" && <Avatar title={video.channel.title} color={video.channel.avatar_color} size={24} />}
          {video.channel.title}
        </Link>
        {variant === "compact" && <div className="vcard__meta">{meta}</div>}
        {variant === "list" && description && <p className="vcard__desc clamp-2">{description}</p>}
      </div>
    </article>
  );
}

export function VideoGrid({ videos }: { videos: Video[] }) {
  return (
    <div className="video-grid">
      {videos.map((v) => (
        <VideoCard key={v.id} video={v} />
      ))}
    </div>
  );
}

export function VideoGridSkeleton({ count = 12 }: { count?: number }) {
  return (
    <div className="video-grid" aria-hidden="true">
      {Array.from({ length: count }, (_, i) => (
        <div key={i} className="vcard vcard--grid">
          <div className="thumb skeleton" />
          <div className="vcard__body">
            <span className="skeleton skeleton--circle" />
            <div className="vcard__text">
              <span className="skeleton skeleton--line" />
              <span className="skeleton skeleton--line skeleton--short" />
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
