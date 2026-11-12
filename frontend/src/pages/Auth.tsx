import { useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { Button, Logo, TextField } from "../components/ui";
import { ApiError, errorText } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useDocumentTitle } from "../lib/hooks";
import "./pages.css";

/** Only same-site relative paths are accepted as a redirect target (no open redirect). */
function safeNext(raw: string | null): string {
  if (raw && raw.startsWith("/") && !raw.startsWith("//") && !raw.startsWith("/\\")) return raw;
  return "/";
}

export function Login() {
  useDocumentTitle("Вход");
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const next = safeNext(params.get("next"));
  const [form, setForm] = useState({ login: "", password: "" });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (user) return <Navigate to={next} replace />;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(form.login.trim(), form.password);
      navigate(next, { replace: true });
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="auth-page">
      <form className="auth-card" onSubmit={submit}>
        <Logo />
        <h1>Вход</h1>
        <p className="text-secondary">Используйте аккаунт Vidora</p>
        <TextField
          label="Email или имя пользователя"
          autoComplete="username"
          required
          value={form.login}
          onChange={(e) => setForm({ ...form, login: e.target.value })}
        />
        <TextField
          label="Пароль"
          type="password"
          autoComplete="current-password"
          required
          value={form.password}
          onChange={(e) => setForm({ ...form, password: e.target.value })}
        />
        {error && <p className="error-text" role="alert">{error}</p>}
        <div className="auth-card__actions">
          <Link to={`/register?next=${encodeURIComponent(next)}`} className="btn btn--ghost btn--md auth-link">
            Создать аккаунт
          </Link>
          <Button variant="accent" type="submit" disabled={busy}>
            {busy ? "Входим…" : "Далее"}
          </Button>
        </div>
      </form>
    </div>
  );
}

export function Register() {
  useDocumentTitle("Регистрация");
  const { user, register } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const next = safeNext(params.get("next"));
  const [form, setForm] = useState({ email: "", username: "", password: "", confirm: "" });
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  if (user) return <Navigate to={next} replace />;

  const validate = (): Record<string, string> => {
    const errs: Record<string, string> = {};
    if (!/^[A-Za-z0-9_.-]{3,30}$/.test(form.username)) errs.username = "3-30 символов: латиница, цифры, _ . -";
    if (form.password.length < 8) errs.password = "Не короче 8 символов";
    else if (/^\d+$/.test(form.password) || /^[A-Za-zА-Яа-я]+$/.test(form.password))
      errs.password = "Добавьте цифры или символы";
    if (form.confirm !== form.password) errs.confirm = "Пароли не совпадают";
    return errs;
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const errs = validate();
    setFieldErrors(errs);
    if (Object.keys(errs).length) return;
    setBusy(true);
    setError(null);
    try {
      await register({ email: form.email.trim(), username: form.username.trim(), password: form.password });
      navigate(next, { replace: true });
    } catch (err) {
      if (err instanceof ApiError && err.code === "username_taken") setFieldErrors({ username: errorText(err) });
      else if (err instanceof ApiError && err.code === "email_taken") setFieldErrors({ email: errorText(err) });
      else setError(errorText(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="auth-page">
      <form className="auth-card" onSubmit={submit} noValidate>
        <Logo />
        <h1>Создайте аккаунт</h1>
        <p className="text-secondary">Канал создаётся автоматически</p>
        <TextField
          label="Email"
          type="email"
          autoComplete="email"
          required
          value={form.email}
          error={fieldErrors.email}
          onChange={(e) => setForm({ ...form, email: e.target.value })}
        />
        <TextField
          label="Имя пользователя (оно же адрес канала)"
          autoComplete="username"
          required
          value={form.username}
          error={fieldErrors.username}
          hint="Латиница, цифры, _ . -"
          onChange={(e) => setForm({ ...form, username: e.target.value })}
        />
        <TextField
          label="Пароль"
          type="password"
          autoComplete="new-password"
          required
          value={form.password}
          error={fieldErrors.password}
          hint="Минимум 8 символов, буквы и цифры"
          onChange={(e) => setForm({ ...form, password: e.target.value })}
        />
        <TextField
          label="Повторите пароль"
          type="password"
          autoComplete="new-password"
          required
          value={form.confirm}
          error={fieldErrors.confirm}
          onChange={(e) => setForm({ ...form, confirm: e.target.value })}
        />
        {error && <p className="error-text" role="alert">{error}</p>}
        <div className="auth-card__actions">
          <Link to={`/login?next=${encodeURIComponent(next)}`} className="btn btn--ghost btn--md auth-link">
            Уже есть аккаунт
          </Link>
          <Button variant="accent" type="submit" disabled={busy}>
            {busy ? "Создаём…" : "Зарегистрироваться"}
          </Button>
        </div>
      </form>
    </div>
  );
}
