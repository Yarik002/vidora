function plural(n: number, one: string, few: string, many: string): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return one;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return few;
  return many;
}

/** 950 -> "950", 1500 -> "1,5 тыс.", 2300000 -> "2,3 млн" */
export function compactNumber(n: number): string {
  const fmt = (v: number) => v.toLocaleString("ru-RU", { maximumFractionDigits: v < 10 ? 1 : 0 });
  if (n < 1000) return String(n);
  if (n < 1_000_000) return `${fmt(n / 1000)} тыс.`;
  if (n < 1_000_000_000) return `${fmt(n / 1_000_000)} млн`;
  return `${fmt(n / 1_000_000_000)} млрд`;
}

export function viewsText(n: number): string {
  if (n === 0) return "Нет просмотров";
  return `${compactNumber(n)} ${plural(n, "просмотр", "просмотра", "просмотров")}`;
}

export function subscribersText(n: number): string {
  if (n === 0) return "Нет подписчиков";
  return `${compactNumber(n)} ${plural(n, "подписчик", "подписчика", "подписчиков")}`;
}

export function countText(n: number, one: string, few: string, many: string): string {
  return `${compactNumber(n)} ${plural(n, one, few, many)}`;
}

export function timeAgo(iso: string | null): string {
  if (!iso) return "";
  const seconds = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  const units: [number, string, string, string][] = [
    [365 * 24 * 3600, "год", "года", "лет"],
    [30 * 24 * 3600, "месяц", "месяца", "месяцев"],
    [7 * 24 * 3600, "неделю", "недели", "недель"],
    [24 * 3600, "день", "дня", "дней"],
    [3600, "час", "часа", "часов"],
    [60, "минуту", "минуты", "минут"],
  ];
  for (const [size, one, few, many] of units) {
    const value = Math.floor(seconds / size);
    if (value >= 1) return `${value} ${plural(value, one, few, many)} назад`;
  }
  return "только что";
}

export function duration(seconds: number | null): string {
  if (seconds == null) return "";
  const s = Math.round(seconds);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = String(s % 60).padStart(2, "0");
  return h > 0 ? `${h}:${String(m).padStart(2, "0")}:${sec}` : `${m}:${sec}`;
}

export function fullDate(iso: string | null): string {
  if (!iso) return "";
  return new Date(iso).toLocaleDateString("ru-RU", { day: "numeric", month: "short", year: "numeric" });
}

export function fileSize(bytes: number): string {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} КБ`;
  if (bytes < 1024 ** 3) return `${(bytes / 1024 / 1024).toFixed(1)} МБ`;
  return `${(bytes / 1024 ** 3).toFixed(2)} ГБ`;
}
