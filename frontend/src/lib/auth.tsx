import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, refreshSession, setSessionExpiredHandler } from "./api";
import type { Me } from "./types";

interface AuthState {
  user: Me | null;
  loading: boolean;
  login: (login: string, password: string) => Promise<void>;
  register: (data: { email: string; username: string; password: string }) => Promise<void>;
  logout: () => Promise<void>;
  reload: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

// Access token lives 15 minutes; refresh a bit earlier while a tab is open.
const REFRESH_EVERY_MS = 12 * 60 * 1000;

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);

  const reload = useCallback(async () => {
    try {
      setUser(await api<Me>("/auth/me"));
    } catch {
      // access cookie expired or absent: try the refresh token once
      if (await refreshSession()) {
        try {
          setUser(await api<Me>("/auth/me", { retry: false }));
          return;
        } catch {
          /* fall through */
        }
      }
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    setSessionExpiredHandler(() => setUser(null));
    void reload();
  }, [reload]);

  useEffect(() => {
    if (!user) return;
    const id = window.setInterval(() => void refreshSession(), REFRESH_EVERY_MS);
    return () => window.clearInterval(id);
  }, [user]);

  const value = useMemo<AuthState>(
    () => ({
      user,
      loading,
      reload,
      login: async (login, password) => {
        setUser(await api<Me>("/auth/login", { method: "POST", body: { login, password } }));
      },
      register: async (data) => {
        setUser(await api<Me>("/auth/register", { method: "POST", body: data }));
      },
      logout: async () => {
        try {
          await api("/auth/logout", { method: "POST" });
        } finally {
          setUser(null);
        }
      },
    }),
    [user, loading, reload],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth outside AuthProvider");
  return ctx;
}

export function isStaff(user: Me | null): boolean {
  return user?.role === "moderator" || user?.role === "admin";
}
