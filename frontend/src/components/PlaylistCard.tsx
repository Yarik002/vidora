import { Link } from "react-router-dom";
import { timeAgo } from "../lib/format";
import type { Playlist } from "../lib/types";
import { Icon } from "./Icon";
import "./VideoCard.css";

export function PlaylistCard({ playlist }: { playlist: Playlist }) {
  return (
    <article className="vcard vcard--grid">
      <Link to={`/playlist/${playlist.id}`} className="thumb thumb--playlist">
        {playlist.thumbnail_url ? <img src={playlist.thumbnail_url} alt="" loading="lazy" /> : <span className="thumb__placeholder"><Icon name="playlist" size={40} /></span>}
        <span className="thumb__duration thumb__count">
          <Icon name="playlist" size={16} />
          {playlist.items_count} видео
        </span>
      </Link>
      <div className="vcard__text vcard__text--playlist">
        <Link to={`/playlist/${playlist.id}`} className="vcard__title clamp-2">
          {playlist.title}
        </Link>
        <span className="vcard__meta">
          {playlist.channel.title} • {playlist.visibility === "private" ? "Ограниченный доступ" : playlist.visibility === "unlisted" ? "По ссылке" : "Открытый"}
        </span>
        <span className="vcard__meta">Обновлён {timeAgo(playlist.updated_at)}</span>
        <Link to={`/playlist/${playlist.id}`} className="vcard__meta vcard__channel">
          Посмотреть весь плейлист
        </Link>
      </div>
    </article>
  );
}

export function PlaylistGrid({ playlists }: { playlists: Playlist[] }) {
  return (
    <div className="video-grid">
      {playlists.map((p) => (
        <PlaylistCard key={p.id} playlist={p} />
      ))}
    </div>
  );
}
