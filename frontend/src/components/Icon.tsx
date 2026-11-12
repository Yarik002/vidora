/**
 * Own icon set: simple 24x24 outline glyphs drawn for Vidora (not copied from any brand kit).
 */
const PATHS: Record<string, string> = {
  menu: "M3 6h18M3 12h18M3 18h18",
  search: "M10.5 4a6.5 6.5 0 1 0 0 13 6.5 6.5 0 0 0 0-13zM20 20l-4.8-4.8",
  home: "M4 10.5 12 4l8 6.5V20h-5.5v-6h-5v6H4z",
  subscriptions: "M5 6h14M7 3h10M4 9h16v11H4zM10 12v5l4-2.5z",
  history: "M12 7v5l3 2M4.5 12a7.5 7.5 0 1 0 2.2-5.3M4 4v4h4",
  playlist: "M4 6h12M4 11h12M4 16h7M15 14v6l5-3z",
  videos: "M4 5h16v14H4zM10 9v6l5-3z",
  like: "M7 21H4V10h3zM7 10l4-7c1.7 0 2.6 1.2 2.2 2.8L12.5 9H19a2 2 0 0 1 2 2.3l-1.2 7.4A2.6 2.6 0 0 1 17.2 21H7",
  dislike: "M17 3h3v11h-3zM17 14l-4 7c-1.7 0-2.6-1.2-2.2-2.8L11.5 15H5a2 2 0 0 1-2-2.3l1.2-7.4A2.6 2.6 0 0 1 6.8 3H17",
  share: "M14 5l6 6-6 6v-4c-5 0-8 1.5-10 5 .5-5.5 3.5-9.5 10-10z",
  save: "M4 6h11M4 11h11M4 16h7M18 13v8M14 17h8",
  more: "M12 5.5v.01M12 12v.01M12 18.5v.01",
  upload: "M4 7h11v10H4zM15 10.5l5-3v9l-5-3M9.5 9.5v5M7 12h5",
  user: "M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4 21c.8-4 4-6 8-6s7.2 2 8 6",
  logout: "M10 4H5v16h5M14 8l4 4-4 4M18 12H9",
  flag: "M5 21V4M5 4h11l-2 4 2 4H5",
  shield: "M12 3 5 6v6c0 4.5 3 7.8 7 9 4-1.2 7-4.5 7-9V6z",
  moon: "M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z",
  sun: "M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8zM12 2v2M12 20v2M4.2 4.2l1.4 1.4M18.4 18.4l1.4 1.4M2 12h2M20 12h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4",
  check: "M5 12.5 10 17 19 7",
  close: "M6 6l12 12M18 6 6 18",
  chevronDown: "M6 9l6 6 6-6",
  chevronUp: "M6 15l6-6 6 6",
  sort: "M4 7h16M7 12h10M10 17h4",
  settings: "M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6zM19.4 13.5l1.6 1.2-2 3.4-1.9-.7a7 7 0 0 1-1.7 1L15 20.5h-4l-.4-2.1a7 7 0 0 1-1.7-1l-1.9.7-2-3.4 1.6-1.2a7 7 0 0 1 0-3L5 9.3l2-3.4 1.9.7a7 7 0 0 1 1.7-1L11 3.5h4l.4 2.1a7 7 0 0 1 1.7 1l1.9-.7 2 3.4-1.6 1.2a7 7 0 0 1 0 3z",
  trash: "M5 7h14M10 7V4h4v3M7 7l1 13h8l1-13",
  edit: "M4 20h4L19 9l-4-4L4 16zM13.5 6.5l4 4",
  lock: "M7 11V8a5 5 0 0 1 10 0v3M5 11h14v10H5z",
  link: "M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1",
  globe: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM3 12h18M12 3c2.5 2.5 3.5 5.5 3.5 9s-1 6.5-3.5 9c-2.5-2.5-3.5-5.5-3.5-9s1-6.5 3.5-9z",
  bell: "M6 17V11a6 6 0 0 1 12 0v6l2 2H4zM10 21h4",
  eyeOff: "M3 3l18 18M10.6 6.1A9.8 9.8 0 0 1 12 6c5 0 8.5 4 9.5 6-.5 1-1.5 2.5-3 3.8M6.5 7.6C4.6 8.9 3.2 10.7 2.5 12c1 2 4.5 6 9.5 6 1.6 0 3-.4 4.3-1",
  eye: "M2.5 12C3.5 10 7 6 12 6s8.5 4 9.5 6c-1 2-4.5 6-9.5 6s-8.5-4-9.5-6zM12 9.5a2.5 2.5 0 1 0 0 5 2.5 2.5 0 0 0 0-5z",
  plus: "M12 5v14M5 12h14",
  reply: "M10 8 5 12l5 4M5 12h9a5 5 0 0 1 5 5v1",
  film: "M4 4h16v16H4zM8 4v16M16 4v16M4 8h4M4 12h4M4 16h4M16 8h4M16 12h4M16 16h4",
  users: "M9 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7zM2.5 20c.6-3.4 3.2-5 6.5-5s5.9 1.6 6.5 5M16 4.5a3.5 3.5 0 0 1 0 6.5M18 15c2 .6 3.3 2.2 3.6 5",
};

export type IconName = keyof typeof PATHS;

export function Icon({ name, size = 24, className }: { name: IconName; size?: number; className?: string }) {
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.7}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      <path d={PATHS[name]} />
    </svg>
  );
}
