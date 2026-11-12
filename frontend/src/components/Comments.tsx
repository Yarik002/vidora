import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, errorText } from "../lib/api";
import { useAuth } from "../lib/auth";
import { countText, timeAgo } from "../lib/format";
import { useInfiniteScroll, usePaged } from "../lib/hooks";
import type { Comment } from "../lib/types";
import { Icon } from "./Icon";
import { ReportDialog } from "./ReportDialog";
import { Avatar, Button, IconButton, Menu, Spinner } from "./ui";
import "./Comments.css";

function CommentForm({
  placeholder,
  onSubmit,
  onCancel,
  autoFocus,
  initial = "",
  submitLabel = "Оставить комментарий",
}: {
  placeholder: string;
  onSubmit: (body: string) => Promise<void>;
  onCancel?: () => void;
  autoFocus?: boolean;
  initial?: string;
  submitLabel?: string;
}) {
  const { user } = useAuth();
  const [body, setBody] = useState(initial);
  const [focused, setFocused] = useState(Boolean(autoFocus));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (!user) return null;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!body.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await onSubmit(body.trim());
      setBody("");
      setFocused(false);
      onCancel?.();
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="comment-form" onSubmit={submit}>
      <Avatar title={user.channel.title} color={user.channel.avatar_color} size={onCancel ? 24 : 40} />
      <div className="comment-form__main">
        <textarea
          className="comment-form__input"
          placeholder={placeholder}
          value={body}
          rows={1}
          maxLength={5000}
          autoFocus={autoFocus}
          onFocus={() => setFocused(true)}
          onChange={(e) => {
            setBody(e.target.value);
            e.target.style.height = "auto";
            e.target.style.height = `${e.target.scrollHeight}px`;
          }}
        />
        {error && <p className="error-text">{error}</p>}
        {focused && (
          <div className="comment-form__actions">
            <Button
              variant="ghost"
              onClick={() => {
                setBody(initial);
                setFocused(false);
                onCancel?.();
              }}
            >
              Отмена
            </Button>
            <Button variant="accent" type="submit" disabled={busy || !body.trim()}>
              {submitLabel}
            </Button>
          </div>
        )}
      </div>
    </form>
  );
}

function CommentItem({
  comment,
  videoId,
  onDeleted,
  onReplyAdded,
}: {
  comment: Comment;
  videoId: string;
  onDeleted: (id: string) => void;
  onReplyAdded?: () => void;
}) {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [state, setState] = useState(comment);
  const [replying, setReplying] = useState(false);
  const [editing, setEditing] = useState(false);
  const [showReplies, setShowReplies] = useState(false);
  const [reporting, setReporting] = useState(false);
  const replies = usePaged<Comment>(showReplies ? `/comments/${comment.id}/replies` : null, 20);

  useEffect(() => setState(comment), [comment]);
  useEffect(() => {
    if (showReplies && replies.items.length === 0 && replies.hasMore && !replies.loading) void replies.loadMore();
  }, [showReplies, replies]);

  const like = async () => {
    if (!user) return navigate("/login");
    const value = state.my_reaction === 1 ? 0 : 1;
    const r = await api<{ likes_count: number; my_reaction: number }>(`/comments/${state.id}/reaction`, {
      method: "PUT",
      body: { value },
    });
    setState({ ...state, ...r });
  };

  const remove = async () => {
    if (!window.confirm("Удалить комментарий?")) return;
    await api(`/comments/${state.id}`, { method: "DELETE" });
    onDeleted(state.id);
  };

  const author = state.author;
  return (
    <div className={`comment ${state.parent_id ? "comment--reply" : ""}`}>
      {author ? (
        <Avatar title={author.channel_title} color={author.avatar_color} size={state.parent_id ? 24 : 40} to={`/channel/${author.channel_handle}`} />
      ) : (
        <span className="comment__deleted-avatar" />
      )}
      <div className="comment__main">
        <div className="comment__head">
          {author ? (
            <Link to={`/channel/${author.channel_handle}`} className={`comment__author ${state.is_video_owner ? "comment__author--owner" : ""}`}>
              @{author.channel_handle}
            </Link>
          ) : (
            <span className="text-secondary">Комментарий удалён</span>
          )}
          <span className="text-secondary">
            {timeAgo(state.created_at)}
            {state.edited && " (изменено)"}
          </span>
        </div>
        {editing ? (
          <CommentForm
            placeholder="Изменить комментарий"
            initial={state.body ?? ""}
            autoFocus
            submitLabel="Сохранить"
            onCancel={() => setEditing(false)}
            onSubmit={async (body) => {
              const updated = await api<Comment>(`/comments/${state.id}`, { method: "PATCH", body: { body } });
              setState(updated);
            }}
          />
        ) : (
          <p className="comment__body">{state.body ?? "[удалено]"}</p>
        )}
        {!state.is_deleted && (
          <div className="comment__actions">
            <button type="button" className={`comment__like ${state.my_reaction === 1 ? "is-active" : ""}`} onClick={like} aria-label="Нравится">
              <Icon name="like" size={18} />
            </button>
            {state.likes_count > 0 && <span className="text-secondary">{state.likes_count}</span>}
            {user && (
              <Button variant="ghost" size="sm" onClick={() => setReplying(true)}>
                Ответить
              </Button>
            )}
            {user && (
              <Menu
                items={[
                  ...(state.can_edit ? [{ icon: "edit" as const, label: "Изменить", onClick: () => setEditing(true) }] : []),
                  ...(state.can_delete ? [{ icon: "trash" as const, label: "Удалить", onClick: remove, danger: true }] : []),
                  { icon: "flag" as const, label: "Пожаловаться", onClick: () => setReporting(true) },
                ]}
                trigger={(props) => <IconButton icon="more" label="Действия" className="comment__menu" {...props} />}
              />
            )}
          </div>
        )}
        {replying && (
          <CommentForm
            placeholder="Введите ответ"
            autoFocus
            submitLabel="Ответить"
            onCancel={() => setReplying(false)}
            onSubmit={async (body) => {
              const created = await api<Comment>(`/videos/${videoId}/comments`, {
                method: "POST",
                body: { body, parent_id: state.id },
              });
              const top = state.parent_id === null;
              if (top) {
                setState((s) => ({ ...s, replies_count: s.replies_count + 1 }));
                setShowReplies(true);
                replies.setItems((items) => [...items, created]);
              } else {
                onReplyAdded?.();
              }
            }}
          />
        )}
        {state.parent_id === null && state.replies_count > 0 && (
          <button type="button" className="comment__replies-toggle" onClick={() => setShowReplies((s) => !s)}>
            <Icon name={showReplies ? "chevronUp" : "chevronDown"} size={20} />
            {countText(state.replies_count, "ответ", "ответа", "ответов")}
          </button>
        )}
        {showReplies && (
          <div className="comment__replies">
            {replies.items.map((r) => (
              <CommentItem
                key={r.id}
                comment={r}
                videoId={videoId}
                onDeleted={(id) => {
                  replies.setItems((items) => items.filter((x) => x.id !== id));
                  setState((s) => ({ ...s, replies_count: Math.max(0, s.replies_count - 1) }));
                }}
                onReplyAdded={() => {
                  setShowReplies(false);
                  setTimeout(() => setShowReplies(true), 0);
                }}
              />
            ))}
            {replies.loading && <Spinner size={24} />}
            {replies.hasMore && !replies.loading && replies.items.length > 0 && (
              <button type="button" className="comment__replies-toggle" onClick={() => void replies.loadMore()}>
                Другие ответы
              </button>
            )}
          </div>
        )}
      </div>
      {reporting && <ReportDialog target={{ comment_id: state.id }} onClose={() => setReporting(false)} />}
    </div>
  );
}

export function Comments({ videoId, count }: { videoId: string; count: number }) {
  const { user } = useAuth();
  const [sort, setSort] = useState<"top" | "new">("top");
  const [total, setTotal] = useState(count);
  const list = usePaged<Comment>(`/videos/${videoId}/comments?sort=${sort}`, 20);
  const sentinel = useInfiniteScroll(() => void list.loadMore(), list.hasMore && !list.loading);

  useEffect(() => setTotal(count), [count]);
  useEffect(() => {
    if (list.items.length === 0 && list.hasMore && !list.loading) void list.loadMore();
  }, [list]);

  return (
    <section className="comments" aria-label="Комментарии">
      <div className="comments__header">
        <h2>{countText(total, "комментарий", "комментария", "комментариев")}</h2>
        <Menu
          align="left"
          items={[
            { label: "Сначала популярные", onClick: () => setSort("top") },
            { label: "Сначала новые", onClick: () => setSort("new") },
          ]}
          trigger={(props) => (
            <Button variant="ghost" icon="sort" {...props}>
              Упорядочить
            </Button>
          )}
        />
      </div>
      {user ? (
        <CommentForm
          placeholder="Введите комментарий"
          onSubmit={async (body) => {
            const created = await api<Comment>(`/videos/${videoId}/comments`, { method: "POST", body: { body } });
            list.setItems((items) => [created, ...items]);
            setTotal((t) => t + 1);
          }}
        />
      ) : (
        <p className="text-secondary comments__signin">
          <Link to={`/login?next=/watch/${videoId}`} className="link-accent">
            Войдите
          </Link>
          , чтобы оставить комментарий.
        </p>
      )}
      {list.items.map((c) => (
        <CommentItem
          key={c.id}
          comment={c}
          videoId={videoId}
          onDeleted={(id) => {
            list.setItems((items) => items.filter((x) => x.id !== id || x.replies_count > 0));
            setTotal((t) => Math.max(0, t - 1));
          }}
        />
      ))}
      <div ref={sentinel}>{list.loading && <Spinner size={28} />}</div>
    </section>
  );
}
