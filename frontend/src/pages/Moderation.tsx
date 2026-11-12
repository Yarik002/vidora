import { useEffect, useState } from "react";
import { Link, Navigate, useSearchParams } from "react-router-dom";
import { Icon } from "../components/Icon";
import { Button, Chip, EmptyState, PageSpinner, Spinner } from "../components/ui";
import { Thumbnail, VideoCard } from "../components/VideoCard";
import { api, errorText } from "../lib/api";
import { isStaff, useAuth } from "../lib/auth";
import { fullDate, timeAgo } from "../lib/format";
import { useDocumentTitle, usePaged } from "../lib/hooks";
import type { AdminUser, ModerationAction, Report, ReportReason, Role, VideoCard as Card } from "../lib/types";
import "./studio.css";

const REASON: Record<ReportReason, string> = {
  spam: "Спам",
  violence: "Насилие",
  hate: "Оскорбления",
  sexual: "18+",
  copyright: "Авторские права",
  misleading: "Дезинформация",
  other: "Другое",
};
const ACTION: Record<string, string> = {
  hide_video: "Скрыто видео",
  restore_video: "Восстановлено видео",
  delete_comment: "Удалён комментарий",
  dismiss_report: "Жалоба отклонена",
  ban_user: "Заблокирован пользователь",
  unban_user: "Разблокирован пользователь",
  change_role: "Изменена роль",
};

function useAutoLoad<T>(list: ReturnType<typeof usePaged<T>>) {
  useEffect(() => {
    if (list.items.length === 0 && list.hasMore && !list.loading) void list.loadMore();
  }, [list]);
}

function ask(text: string): string | null {
  const reason = window.prompt(text, "");
  return reason === null ? null : reason.trim();
}

function Reports() {
  const [status, setStatus] = useState<"open" | "resolved" | "dismissed">("open");
  const list = usePaged<Report>(`/moderation/reports?status=${status}`, 30);
  useAutoLoad(list);
  const [error, setError] = useState<string | null>(null);

  const act = async (fn: () => Promise<unknown>, reportId: string) => {
    setError(null);
    try {
      await fn();
      list.setItems((items) => items.filter((r) => r.id !== reportId));
    } catch (err) {
      setError(errorText(err));
    }
  };

  return (
    <>
      <div className="row mod-filters">
        <Chip active={status === "open"} onClick={() => setStatus("open")}>
          Новые
        </Chip>
        <Chip active={status === "resolved"} onClick={() => setStatus("resolved")}>
          Решённые
        </Chip>
        <Chip active={status === "dismissed"} onClick={() => setStatus("dismissed")}>
          Отклонённые
        </Chip>
      </div>
      {error && <p className="error-text">{error}</p>}
      {!list.loading && list.items.length === 0 && <EmptyState icon="shield" title="Жалоб нет" />}
      <div className="reports">
        {list.items.map((r) => (
          <article key={r.id} className="report">
            <div className="report__target">
              {r.video ? (
                <>
                  <Thumbnail video={r.video} size="sm" />
                  <div>
                    <Link to={`/watch/${r.video.id}`} className="clamp-2 report__title">
                      {r.video.title}
                    </Link>
                    <span className="text-secondary">{r.video.channel.title}</span>
                    {r.video_moderation_state === "hidden" && <span className="badge badge--danger">Скрыто</span>}
                  </div>
                </>
              ) : r.comment ? (
                <div className="report__comment">
                  <span className="text-secondary">Комментарий @{r.comment.author}:</span>
                  <p>{r.comment.body ?? "[удалён]"}</p>
                  <Link to={`/watch/${r.comment.video_id}`} className="link-accent">
                    Открыть видео
                  </Link>
                </div>
              ) : (
                <span className="text-secondary">Объект удалён</span>
              )}
            </div>
            <div className="report__meta">
              <span className="badge">{REASON[r.reason]}</span>
              {r.reports_on_target > 1 && <span className="badge badge--danger">{r.reports_on_target} жалоб(ы)</span>}
              <span className="text-secondary">
                от @{r.reporter ?? "удалён"} • {timeAgo(r.created_at)}
              </span>
              {r.details && <p className="report__details">«{r.details}»</p>}
            </div>
            {r.status === "open" && (
              <div className="report__actions">
                {r.video && r.video_moderation_state !== "hidden" && (
                  <Button
                    variant="danger"
                    icon="eyeOff"
                    onClick={() => {
                      const reason = ask("Причина скрытия (увидит журнал модерации)");
                      if (reason !== null)
                        void act(() => api(`/moderation/videos/${r.video!.id}/hide`, { method: "POST", body: { reason, report_id: r.id } }), r.id);
                    }}
                  >
                    Скрыть видео
                  </Button>
                )}
                {r.comment && r.comment.body && (
                  <Button
                    variant="danger"
                    icon="trash"
                    onClick={() => {
                      const reason = ask("Причина удаления комментария");
                      if (reason !== null)
                        void act(() => api(`/moderation/comments/${r.comment!.id}/delete`, { method: "POST", body: { reason, report_id: r.id } }), r.id);
                    }}
                  >
                    Удалить комментарий
                  </Button>
                )}
                <Button
                  icon="check"
                  onClick={() => void act(() => api(`/moderation/reports/${r.id}/dismiss`, { method: "POST", body: { reason: "Нарушений нет" } }), r.id)}
                >
                  Нарушений нет
                </Button>
              </div>
            )}
          </article>
        ))}
      </div>
      {list.loading && <Spinner />}
      {list.hasMore && !list.loading && (
        <Button onClick={() => void list.loadMore()}>Показать ещё</Button>
      )}
    </>
  );
}

function Hidden() {
  const list = usePaged<Card>("/moderation/videos/hidden", 30);
  useAutoLoad(list);
  return (
    <>
      {!list.loading && list.items.length === 0 && <EmptyState icon="eye" title="Скрытых видео нет" />}
      <div className="hidden-list">
        {list.items.map((v) => (
          <div key={v.id} className="row hidden-list__item">
            <div className="spacer">
              <VideoCard video={v} variant="compact" />
            </div>
            <Button
              icon="eye"
              onClick={async () => {
                const reason = ask("Почему восстанавливаете?");
                if (reason === null) return;
                await api(`/moderation/videos/${v.id}/restore`, { method: "POST", body: { reason } });
                list.setItems((items) => items.filter((x) => x.id !== v.id));
              }}
            >
              Восстановить
            </Button>
          </div>
        ))}
      </div>
      {list.loading && <Spinner />}
    </>
  );
}

function Log() {
  const list = usePaged<ModerationAction>("/moderation/actions", 50);
  useAutoLoad(list);
  return (
    <div className="studio-table" role="table" aria-label="Журнал модерации">
      <div className="log-row studio-row--head" role="row">
        <span>Когда</span>
        <span>Кто</span>
        <span>Действие</span>
        <span>Объект</span>
        <span>Причина</span>
      </div>
      {list.items.map((a) => (
        <div key={a.id} className="log-row" role="row">
          <span className="text-secondary">{fullDate(a.created_at)}</span>
          <span>@{a.moderator ?? "?"}</span>
          <span>{ACTION[a.action] ?? a.action}</span>
          <span>
            {a.video_id ? (
              <Link to={`/watch/${a.video_id}`} className="link-accent">
                {a.video_title ?? "видео"}
              </Link>
            ) : a.target_user ? (
              `@${a.target_user}`
            ) : (
              "-"
            )}
          </span>
          <span className="text-secondary">{a.reason || "-"}</span>
        </div>
      ))}
      {list.loading && <Spinner />}
      {list.hasMore && !list.loading && <Button onClick={() => void list.loadMore()}>Показать ещё</Button>}
    </div>
  );
}

function Users() {
  const { user: me } = useAuth();
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  const list = usePaged<AdminUser>(`/admin/users${query ? `?q=${encodeURIComponent(query)}` : ""}`, 50);
  useAutoLoad(list);
  const [error, setError] = useState<string | null>(null);

  const update = async (u: AdminUser, body: { role?: Role; is_active?: boolean }) => {
    setError(null);
    let reason = "";
    if (body.is_active === false) {
      const r = ask(`Причина блокировки @${u.username}`);
      if (r === null) return;
      reason = r;
    }
    try {
      const updated = await api<AdminUser>(`/admin/users/${u.id}`, { method: "PATCH", body: { ...body, reason } });
      list.setItems((items) => items.map((x) => (x.id === u.id ? updated : x)));
    } catch (err) {
      setError(errorText(err));
    }
  };

  return (
    <>
      <form
        className="row mod-filters"
        onSubmit={(e) => {
          e.preventDefault();
          setQuery(q.trim());
        }}
      >
        <input className="field__input users-search" placeholder="Поиск по имени или email" value={q} onChange={(e) => setQ(e.target.value)} />
        <Button type="submit" icon="search">
          Найти
        </Button>
      </form>
      {error && <p className="error-text">{error}</p>}
      <div className="studio-table" role="table" aria-label="Пользователи">
        <div className="user-row studio-row--head" role="row">
          <span>Пользователь</span>
          <span>Email</span>
          <span>Роль</span>
          <span>Видео</span>
          <span>Последний вход</span>
          <span>Статус</span>
        </div>
        {list.items.map((u) => (
          <div key={u.id} className="user-row" role="row">
            <Link to={`/channel/${u.username.toLowerCase()}`}>@{u.username}</Link>
            <span className="text-secondary">{u.email}</span>
            <select
              className="field__input"
              value={u.role}
              disabled={u.id === me?.id}
              aria-label={`Роль @${u.username}`}
              onChange={(e) => void update(u, { role: e.target.value as Role })}
            >
              <option value="user">Пользователь</option>
              <option value="moderator">Модератор</option>
              <option value="admin">Администратор</option>
            </select>
            <span>{u.videos_count}</span>
            <span className="text-secondary">{u.last_login_at ? timeAgo(u.last_login_at) : "никогда"}</span>
            <span>
              {u.id === me?.id ? (
                <span className="text-secondary">это вы</span>
              ) : u.is_active ? (
                <Button size="sm" variant="ghost" icon="lock" onClick={() => void update(u, { is_active: false })}>
                  Заблокировать
                </Button>
              ) : (
                <Button size="sm" icon="check" onClick={() => void update(u, { is_active: true })}>
                  Разблокировать
                </Button>
              )}
            </span>
          </div>
        ))}
      </div>
      {list.loading && <Spinner />}
    </>
  );
}

type Tab = "reports" | "hidden" | "log" | "users";

export function Moderation() {
  useDocumentTitle("Модерация");
  const { user, loading } = useAuth();
  const [params, setParams] = useSearchParams();
  const tab = (params.get("tab") as Tab) || "reports";
  if (loading) return <PageSpinner />;
  if (!user) return <Navigate to="/login?next=/moderation" replace />;
  if (!isStaff(user)) return <EmptyState icon="lock" title="Раздел доступен только модераторам" />;

  const tabs: [Tab, string][] = [
    ["reports", "Жалобы"],
    ["hidden", "Скрытые видео"],
    ["log", "Журнал"],
    ...(user.role === "admin" ? ([["users", "Пользователи"]] as [Tab, string][]) : []),
  ];
  return (
    <div className="page moderation">
      <h1 className="page-title">
        <Icon name="shield" /> Модерация
      </h1>
      <nav className="channel__tabs" aria-label="Разделы модерации">
        {tabs.map(([key, label]) => (
          <button key={key} type="button" className={`channel__tab ${tab === key ? "is-active" : ""}`} onClick={() => setParams({ tab: key })}>
            {label}
          </button>
        ))}
      </nav>
      <div className="moderation__content">
        {tab === "reports" && <Reports />}
        {tab === "hidden" && <Hidden />}
        {tab === "log" && <Log />}
        {tab === "users" && user.role === "admin" && <Users />}
      </div>
    </div>
  );
}
