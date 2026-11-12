import { useEffect, useState, type FormEvent } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { isStaff, useAuth } from "../lib/auth";
import { useApi } from "../lib/hooks";
import { applyTheme, getTheme, type Theme } from "../lib/theme";
import type { ChannelBrief } from "../lib/types";
import { Icon, type IconName } from "./Icon";
import { Avatar, IconButton, Logo, Menu } from "./ui";
import "./Layout.css";

function SearchBox() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const [q, setQ] = useState(params.get("search_query") ?? "");
  useEffect(() => setQ(params.get("search_query") ?? ""), [params]);
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const query = q.trim();
    if (query) navigate(`/results?search_query=${encodeURIComponent(query)}`);
  };
  return (
    <form className="search" role="search" onSubmit={submit}>
      <input
        className="search__input"
        type="search"
        placeholder="Введите запрос"
        aria-label="Поиск"
        value={q}
        maxLength={100}
        onChange={(e) => setQ(e.target.value)}
      />
      <button className="search__button" type="submit" aria-label="Найти" title="Найти">
        <Icon name="search" />
      </button>
    </form>
  );
}

function UserMenu({ theme, onTheme }: { theme: Theme; onTheme: (t: Theme) => void }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  if (!user) return null;
  return (
    <Menu
      header={
        <div className="user-menu__header">
          <Avatar title={user.channel.title} color={user.channel.avatar_color} size={40} />
          <div>
            <div className="user-menu__name">{user.channel.title}</div>
            <div className="text-secondary">@{user.channel.handle}</div>
            <Link to={`/channel/${user.channel.handle}`} className="user-menu__link">
              Мой канал
            </Link>
          </div>
        </div>
      }
      items={[
        "divider",
        { icon: "videos", label: "Мои видео", to: "/studio" },
        ...(isStaff(user) ? [{ icon: "shield" as IconName, label: "Модерация", to: "/moderation" }] : []),
        {
          icon: theme === "dark" ? "sun" : "moon",
          label: theme === "dark" ? "Светлая тема" : "Тёмная тема",
          onClick: () => onTheme(theme === "dark" ? "light" : "dark"),
        },
        "divider",
        {
          icon: "logout",
          label: "Выйти",
          onClick: async () => {
            await logout();
            navigate("/");
          },
        },
      ]}
      trigger={(props) => (
        <button className="header__avatar" aria-label="Меню аккаунта" {...props}>
          <Avatar title={user.channel.title} color={user.channel.avatar_color} size={32} />
        </button>
      )}
    />
  );
}

function Header({ onMenu }: { onMenu: () => void }) {
  const { user, loading } = useAuth();
  const location = useLocation();
  const [theme, setTheme] = useState<Theme>(getTheme());
  const changeTheme = (t: Theme) => {
    applyTheme(t);
    setTheme(t);
  };
  const next = encodeURIComponent(location.pathname + location.search);
  return (
    <header className="header">
      <div className="header__start">
        <IconButton icon="menu" label="Меню" onClick={onMenu} />
        <Link to="/" aria-label="Vidora, главная" className="header__logo">
          <Logo />
        </Link>
      </div>
      <div className="header__center">
        <SearchBox />
      </div>
      <div className="header__end">
        {!user && (
          <IconButton
            icon={theme === "dark" ? "sun" : "moon"}
            label="Сменить тему"
            onClick={() => changeTheme(theme === "dark" ? "light" : "dark")}
          />
        )}
        {user && (
          <Link to="/upload" className="btn btn--secondary btn--md header__create" title="Загрузить видео">
            <Icon name="plus" size={22} />
            <span>Создать</span>
          </Link>
        )}
        {!loading && !user && (
          <Link to={`/login?next=${next}`} className="btn btn--outline-accent btn--md">
            <Icon name="user" size={22} />
            <span>Войти</span>
          </Link>
        )}
        <UserMenu theme={theme} onTheme={changeTheme} />
      </div>
    </header>
  );
}

function NavItem({ to, icon, label, mini }: { to: string; icon: IconName; label: string; mini: boolean }) {
  return (
    <NavLink to={to} end className={({ isActive }) => `nav-item ${mini ? "nav-item--mini" : ""} ${isActive ? "nav-item--active" : ""}`}>
      <Icon name={icon} />
      <span>{label}</span>
    </NavLink>
  );
}

function Sidebar({ expanded }: { expanded: boolean }) {
  const { user, loading } = useAuth();
  const subs = useApi<ChannelBrief[]>(user && expanded ? "/me/subscriptions" : null);
  if (!expanded) {
    return (
      <nav className="sidebar sidebar--mini" aria-label="Навигация">
        <NavItem to="/" icon="home" label="Главная" mini />
        <NavItem to="/feed/subscriptions" icon="subscriptions" label="Подписки" mini />
        <NavItem to="/feed/you" icon="user" label="Вы" mini />
      </nav>
    );
  }
  return (
    <nav className="sidebar" aria-label="Навигация">
      <section className="sidebar__section">
        <NavItem to="/" icon="home" label="Главная" mini={false} />
        <NavItem to="/feed/subscriptions" icon="subscriptions" label="Подписки" mini={false} />
      </section>
      <section className="sidebar__section">
        <h3 className="sidebar__title">Вы</h3>
        {user ? (
          <>
            <NavItem to={`/channel/${user.channel.handle}`} icon="user" label="Мой канал" mini={false} />
            <NavItem to="/feed/history" icon="history" label="История" mini={false} />
            <NavItem to="/feed/playlists" icon="playlist" label="Плейлисты" mini={false} />
            <NavItem to="/studio" icon="videos" label="Ваши видео" mini={false} />
            <NavItem to="/feed/liked" icon="like" label="Понравившиеся" mini={false} />
          </>
        ) : loading ? null : (
          <div className="sidebar__signin">
            <p>Войдите, чтобы ставить лайки, писать комментарии и подписываться.</p>
            <Link to="/login" className="btn btn--outline-accent btn--md">
              <Icon name="user" size={22} />
              <span>Войти</span>
            </Link>
          </div>
        )}
      </section>
      {user && subs.data && subs.data.length > 0 && (
        <section className="sidebar__section">
          <h3 className="sidebar__title">Подписки</h3>
          {subs.data.slice(0, 10).map((c) => (
            <NavLink key={c.id} to={`/channel/${c.handle}`} className="nav-item">
              <Avatar title={c.title} color={c.avatar_color} size={24} />
              <span>{c.title}</span>
            </NavLink>
          ))}
        </section>
      )}
      {isStaff(user) && (
        <section className="sidebar__section">
          <h3 className="sidebar__title">Управление</h3>
          <NavItem to="/moderation" icon="shield" label="Модерация" mini={false} />
        </section>
      )}
      <footer className="sidebar__footer">
        <a href="/docs" target="_blank" rel="noreferrer">
          API (Swagger)
        </a>
        <p>Vidora: учебный проект, не связан с YouTube.</p>
      </footer>
    </nav>
  );
}

export function Layout() {
  const location = useLocation();
  const isWatch = location.pathname.startsWith("/watch/");
  const wide = () => window.matchMedia("(min-width: 1312px)").matches;
  const [expanded, setExpanded] = useState(() => !isWatch && wide());
  const [drawer, setDrawer] = useState(false);

  // Watch page: sidebar collapses into a drawer like on the reference site.
  useEffect(() => {
    setDrawer(false);
    if (isWatch) setExpanded(false);
    else setExpanded(wide());
  }, [isWatch]);

  const onMenu = () => (isWatch || !wide() ? setDrawer((d) => !d) : setExpanded((e) => !e));

  return (
    <div className={`app ${isWatch ? "app--watch" : expanded ? "app--expanded" : "app--mini"}`}>
      <Header onMenu={onMenu} />
      {!isWatch && <Sidebar expanded={expanded} />}
      {drawer && (
        <div className="drawer" onClick={() => setDrawer(false)}>
          <div className="drawer__panel" onClick={(e) => e.stopPropagation()}>
            <div className="drawer__head">
              <IconButton icon="menu" label="Закрыть меню" onClick={() => setDrawer(false)} />
              <Link to="/" onClick={() => setDrawer(false)}>
                <Logo />
              </Link>
            </div>
            <Sidebar expanded />
          </div>
        </div>
      )}
      <main className="main">
        <Outlet />
      </main>
    </div>
  );
}

