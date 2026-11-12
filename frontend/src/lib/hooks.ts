import { useCallback, useEffect, useRef, useState } from "react";
import { api, errorText } from "./api";
import type { Page } from "./types";

/** GET a resource; re-fetches when `path` changes. `null` path = don't load. */
export function useApi<T>(path: string | null) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(path !== null);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    if (path === null) return;
    const ctrl = new AbortController();
    setLoading(true);
    setError(null);
    api<T>(path, { signal: ctrl.signal })
      .then((d) => setData(d))
      .catch((e) => {
        const text = errorText(e);
        if (text) setError(text);
      })
      .finally(() => {
        if (!ctrl.signal.aborted) setLoading(false);
      });
    return () => ctrl.abort();
  }, [path, version]);

  const reload = useCallback(() => setVersion((v) => v + 1), []);
  return { data, setData, error, loading, reload };
}

/** Offset-paginated list with "load more" (infinite scroll via useInfiniteScroll). */
export function usePaged<T>(basePath: string | null, pageSize = 24) {
  const [items, setItems] = useState<T[]>([]);
  const [hasMore, setHasMore] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const offsetRef = useRef(0);
  const pathRef = useRef(basePath);

  const loadMore = useCallback(async () => {
    const path = pathRef.current;
    if (path === null || loading) return;
    setLoading(true);
    try {
      const sep = path.includes("?") ? "&" : "?";
      const page = await api<Page<T>>(`${path}${sep}offset=${offsetRef.current}&limit=${pageSize}`);
      if (pathRef.current !== path) return; // a newer query replaced this one
      offsetRef.current += page.items.length;
      setItems((prev) => [...prev, ...page.items]);
      setHasMore(page.has_more);
    } catch (e) {
      setError(errorText(e));
      setHasMore(false);
    } finally {
      setLoading(false);
    }
  }, [loading, pageSize]);

  useEffect(() => {
    pathRef.current = basePath;
    offsetRef.current = 0;
    setItems([]);
    setHasMore(basePath !== null);
    setError(null);
  }, [basePath]);

  return { items, setItems, hasMore, loading, error, loadMore };
}

/** Calls `onVisible` when the sentinel element scrolls into view. */
export function useInfiniteScroll(onVisible: () => void, enabled: boolean) {
  const ref = useRef<HTMLDivElement | null>(null);
  const cb = useRef(onVisible);
  cb.current = onVisible;
  useEffect(() => {
    const el = ref.current;
    if (!el || !enabled) return;
    const obs = new IntersectionObserver((entries) => {
      if (entries.some((e) => e.isIntersecting)) cb.current();
    }, { rootMargin: "600px" });
    obs.observe(el);
    return () => obs.disconnect();
  }, [enabled]);
  return ref;
}

export function useDocumentTitle(title: string | undefined) {
  useEffect(() => {
    document.title = title ? `${title} - Vidora` : "Vidora";
  }, [title]);
}
