import { useEffect, useState } from "react";
import { errorText } from "../lib/api";

const EVENT = "vidora-toast";

/** Show a short message at the bottom of the screen (like the reference "snackbar"). */
export function toast(message: string): void {
  window.dispatchEvent(new CustomEvent(EVENT, { detail: message }));
}

/** Report a failed action to the user instead of an unhandled promise rejection. */
export function toastError(err: unknown): void {
  const text = errorText(err);
  if (text) toast(text);
}

export function Toaster() {
  const [message, setMessage] = useState<string | null>(null);
  useEffect(() => {
    let timer = 0;
    const onToast = (e: Event) => {
      setMessage((e as CustomEvent<string>).detail);
      window.clearTimeout(timer);
      timer = window.setTimeout(() => setMessage(null), 4000);
    };
    window.addEventListener(EVENT, onToast);
    return () => {
      window.removeEventListener(EVENT, onToast);
      window.clearTimeout(timer);
    };
  }, []);
  if (!message) return null;
  return (
    <div className="toast" role="status" aria-live="polite">
      {message}
    </div>
  );
}
