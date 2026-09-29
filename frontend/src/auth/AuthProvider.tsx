import { createContext, useCallback, useContext, useEffect, useState, ReactNode } from "react";
import { api } from "@/src/api";
import { clearToken, getToken, saveToken, saveUser, getUser } from "@/src/auth/storage";

type User = {
  id: string;
  email: string;
  name: string;
  role: string;
  job_title?: string;
  department?: string;
  job_code?: string;
  is_admin: boolean;
};

type AuthCtx = {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
};

const AuthContext = createContext<AuthCtx | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const bootstrap = useCallback(async () => {
    try {
      const token = await getToken();
      if (!token) {
        setUser(null);
        setLoading(false);
        return;
      }
      const cached = await getUser();
      if (cached) setUser(cached);
      try {
        const me = await api.me();
        setUser(me);
        await saveUser(me);
      } catch {
        await clearToken();
        setUser(null);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    bootstrap();
  }, [bootstrap]);

  const login = useCallback(async (email: string, password: string) => {
    const res = await api.login(email, password);
    await saveToken(res.access_token);
    await saveUser(res.user);
    setUser(res.user);
  }, []);

  const logout = useCallback(async () => {
    await clearToken();
    setUser(null);
  }, []);

  const refresh = useCallback(async () => {
    const me = await api.me();
    setUser(me);
    await saveUser(me);
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, refresh }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be inside AuthProvider");
  return ctx;
}
