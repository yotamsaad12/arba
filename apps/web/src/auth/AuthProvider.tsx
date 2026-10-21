import type { TokenOut } from "@arba/api-client";
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { api, queryClient } from "../lib/api";

type Status = "loading" | "authenticated" | "anonymous";

interface AuthContextValue {
  status: Status;
  signIn: (tokens: TokenOut) => Promise<void>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<Status>("loading");

  useEffect(() => {
    // The access token lives in memory only; restore it from the refresh cookie on load.
    let active = true;
    void api.refresh().then((ok) => active && setStatus(ok ? "authenticated" : "anonymous"));
    const onExpired = () => setStatus("anonymous");
    window.addEventListener("arba:session-expired", onExpired);
    return () => {
      active = false;
      window.removeEventListener("arba:session-expired", onExpired);
    };
  }, []);

  const signIn = useCallback(async (tokens: TokenOut) => {
    await api.setSession(tokens);
    setStatus("authenticated");
  }, []);

  const signOut = useCallback(async () => {
    await api.fetchClient.POST("/api/v1/auth/logout", { body: null });
    await api.clearSession();
    queryClient.clear();
    setStatus("anonymous");
  }, []);

  const value = useMemo(() => ({ status, signIn, signOut }), [status, signIn, signOut]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}
