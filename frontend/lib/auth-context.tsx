"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import {
  clearTokens,
  getAccessToken,
  getRefreshToken,
  logout as apiLogout,
  storeTokens,
} from "@/lib/auth-api";

interface AuthContextType {
  token: string;
  refreshToken: string;
  isAuthenticated: boolean;
  login: (accessToken: string, refreshToken: string) => void;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function useAuth(): AuthContextType {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within <AuthProvider>");
  return ctx;
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [token, setToken] = useState("");
  const [refreshToken, setRefreshToken] = useState("");
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setToken(getAccessToken());
    setRefreshToken(getRefreshToken());
    setMounted(true);
  }, []);

  const login = useCallback((accessToken: string, refreshToken: string) => {
    storeTokens({ access_token: accessToken, refresh_token: refreshToken });
    setToken(accessToken);
    setRefreshToken(refreshToken);
  }, []);

  const logout = useCallback(async () => {
    try {
      await apiLogout();
    } catch {
      // best-effort
    }
    clearTokens();
    setToken("");
    setRefreshToken("");
  }, []);

  return (
    <AuthContext.Provider
      value={{ token, refreshToken, isAuthenticated: mounted && !!token, login, logout }}
    >
      {children}
    </AuthContext.Provider>
  );
}
