import { useEffect, useRef, useState } from "react";
import type { VideoDetail } from "../lib/types";
import { Icon } from "./Icon";
import "./Player.css";

const QUALITY_KEY = "vidora-quality";

function preferredQuality(available: string[]): string | undefined {
  try {
    const saved = localStorage.getItem(QUALITY_KEY);
    if (saved && available.includes(saved)) return saved;
  } catch {
    /* ignore */
  }
  return available[0];
}

/**
 * Native <video> with a quality switcher. `src` is our API endpoint: it checks access and
 * redirects to a short-lived signed storage URL, so seeking (Range requests) is served by storage.
 * If the signed URL expires during a long pause, the error handler re-requests it and
 * continues from the same position.
 */
export function Player({ video, onFirstPlay }: { video: VideoDetail; onFirstPlay: () => void }) {
  const ref = useRef<HTMLVideoElement>(null);
  const [quality, setQuality] = useState(() => preferredQuality(video.qualities));
  const [menu, setMenu] = useState(false);
  const [nonce, setNonce] = useState(0);
  const resumeAt = useRef(0);
  const played = useRef(false);

  useEffect(() => {
    played.current = false;
    setQuality(preferredQuality(video.qualities));
  }, [video.id, video.qualities]);

  const src = `/api/v1/videos/${video.id}/stream${quality ? `?quality=${quality}` : ""}${nonce ? `${quality ? "&" : "?"}r=${nonce}` : ""}`;

  const switchTo = (q: string) => {
    const el = ref.current;
    resumeAt.current = el?.currentTime ?? 0;
    setQuality(q);
    setMenu(false);
    try {
      localStorage.setItem(QUALITY_KEY, q);
    } catch {
      /* ignore */
    }
  };

  return (
    <div className="player">
      <video
        ref={ref}
        key={src}
        src={src}
        poster={video.thumbnail_url ?? undefined}
        controls
        autoPlay
        playsInline
        preload="metadata"
        onLoadedMetadata={(e) => {
          if (resumeAt.current > 0) {
            e.currentTarget.currentTime = resumeAt.current;
            resumeAt.current = 0;
          }
        }}
        onPlay={() => {
          if (!played.current) {
            played.current = true;
            onFirstPlay();
          }
        }}
        onError={(e) => {
          // most likely an expired signed URL (long pause or a tab left open): ask /stream again
          const el = e.currentTarget;
          if (nonce < 3) {
            resumeAt.current = el.currentTime;
            setNonce((n) => n + 1);
          }
        }}
      />
      {video.qualities.length > 1 && (
        <div className="player__quality">
          <button
            type="button"
            className="player__quality-btn"
            aria-label="Качество видео"
            aria-expanded={menu}
            onClick={() => setMenu((m) => !m)}
          >
            <Icon name="settings" size={20} />
            <span>{quality}</span>
          </button>
          {menu && (
            <ul className="player__quality-menu" role="menu">
              {video.qualities.map((q) => (
                <li key={q}>
                  <button type="button" role="menuitemradio" aria-checked={q === quality} onClick={() => switchTo(q)}>
                    {q === quality && <Icon name="check" size={18} />}
                    <span>{q}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
