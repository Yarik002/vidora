/**
 * Vidora UI kit (see docs/design-system.md). Small, dependency-free components
 * that only use design tokens.
 */
import {
  useEffect,
  useRef,
  useState,
  type ButtonHTMLAttributes,
  type ReactNode,
} from "react";
import { Link } from "react-router-dom";
import { Icon, type IconName } from "./Icon";
import "./ui.css";

type ButtonVariant = "primary" | "secondary" | "ghost" | "outline-accent" | "danger" | "accent";

export function Button({
  variant = "secondary",
  icon,
  size = "md",
  className = "",
  children,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  icon?: IconName;
  size?: "sm" | "md";
}) {
  return (
    <button
      type="button"
      className={`btn btn--${variant} btn--${size} ${children ? "" : "btn--icon-only"} ${className}`}
      {...rest}
    >
      {icon && <Icon name={icon} size={size === "sm" ? 18 : 22} />}
      {children && <span>{children}</span>}
    </button>
  );
}

export function IconButton({
  icon,
  label,
  className = "",
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { icon: IconName; label: string }) {
  return (
    <button type="button" className={`icon-btn ${className}`} aria-label={label} title={label} {...rest}>
      <Icon name={icon} />
    </button>
  );
}

export function Avatar({
  title,
  color,
  size = 36,
  to,
}: {
  title: string;
  color: string;
  size?: number;
  to?: string;
}) {
  const letter = (title.trim()[0] ?? "?").toUpperCase();
  const el = (
    <span
      className="avatar"
      style={{ width: size, height: size, fontSize: size * 0.45, backgroundColor: color }}
      aria-hidden={to ? undefined : true}
    >
      {letter}
    </span>
  );
  return to ? (
    <Link to={to} aria-label={title} className="avatar-link">
      {el}
    </Link>
  ) : (
    el
  );
}

export function Logo() {
  return (
    <span className="logo">
      <svg width="30" height="30" viewBox="0 0 32 32" aria-hidden="true">
        <defs>
          <linearGradient id="vidora-logo" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor="var(--color-brand)" />
            <stop offset="1" stopColor="var(--color-brand-2)" />
          </linearGradient>
        </defs>
        <path d="M16 2 28 9v14L16 30 4 23V9z" fill="url(#vidora-logo)" />
        <path d="M13 11v10l8-5z" fill="#fff" />
      </svg>
      <span className="logo__text">Vidora</span>
    </span>
  );
}

export function Chip({ active, children, onClick }: { active?: boolean; children: ReactNode; onClick?: () => void }) {
  return (
    <button type="button" className={`chip ${active ? "chip--active" : ""}`} onClick={onClick} aria-pressed={active}>
      {children}
    </button>
  );
}

export function Spinner({ size = 32 }: { size?: number }) {
  return <span className="spinner" style={{ width: size, height: size }} role="status" aria-label="Загрузка" />;
}

export function PageSpinner() {
  return (
    <div className="page-spinner">
      <Spinner />
    </div>
  );
}

export function ProgressBar({ value }: { value: number }) {
  return (
    <div className="progress" role="progressbar" aria-valuenow={Math.round(value)} aria-valuemin={0} aria-valuemax={100}>
      <div className="progress__bar" style={{ width: `${Math.min(100, Math.max(0, value))}%` }} />
    </div>
  );
}

export function Modal({
  title,
  onClose,
  children,
  footer,
  wide,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
  wide?: boolean;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    if (dialog && !dialog.open) dialog.showModal();
  }, []);
  return (
    <dialog
      ref={ref}
      className={`modal ${wide ? "modal--wide" : ""}`}
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
      onClick={(e) => {
        if (e.target === ref.current) onClose(); // click on backdrop
      }}
    >
      <div className="modal__header">
        <h2>{title}</h2>
        <IconButton icon="close" label="Закрыть" onClick={onClose} />
      </div>
      <div className="modal__body">{children}</div>
      {footer && <div className="modal__footer">{footer}</div>}
    </dialog>
  );
}

export interface MenuItem {
  icon?: IconName;
  label: string;
  onClick?: () => void;
  to?: string;
  danger?: boolean;
}

/** Dropdown anchored to its trigger; closes on outside click and Escape. */
export function Menu({
  trigger,
  items,
  align = "right",
  header,
}: {
  trigger: (props: { onClick: () => void; "aria-expanded": boolean }) => ReactNode;
  items: (MenuItem | "divider")[];
  align?: "left" | "right";
  header?: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);
  return (
    <div className="menu" ref={ref}>
      {trigger({ onClick: () => setOpen((o) => !o), "aria-expanded": open })}
      {open && (
        <div className={`menu__popup menu__popup--${align}`} role="menu">
          {header}
          {items.map((item, i) =>
            item === "divider" ? (
              <hr key={i} className="menu__divider" />
            ) : item.to ? (
              <Link key={i} to={item.to} className="menu__item" role="menuitem" onClick={() => setOpen(false)}>
                {item.icon && <Icon name={item.icon} />}
                {item.label}
              </Link>
            ) : (
              <button
                key={i}
                type="button"
                role="menuitem"
                className={`menu__item ${item.danger ? "menu__item--danger" : ""}`}
                onClick={() => {
                  setOpen(false);
                  item.onClick?.();
                }}
              >
                {item.icon && <Icon name={item.icon} />}
                {item.label}
              </button>
            ),
          )}
        </div>
      )}
    </div>
  );
}

export function TextField({
  label,
  error,
  hint,
  multiline,
  ...rest
}: {
  label: string;
  error?: string | null;
  hint?: string;
  multiline?: boolean;
} & React.InputHTMLAttributes<HTMLInputElement> &
  React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <label className={`field ${error ? "field--error" : ""}`}>
      <span className="field__label">{label}</span>
      {multiline ? <textarea className="field__input" rows={5} {...rest} /> : <input className="field__input" {...rest} />}
      {(error || hint) && <span className="field__hint">{error || hint}</span>}
    </label>
  );
}

export function EmptyState({ icon, title, children }: { icon: IconName; title: string; children?: ReactNode }) {
  return (
    <div className="empty-state">
      <Icon name={icon} size={64} />
      <h2>{title}</h2>
      {children}
    </div>
  );
}
