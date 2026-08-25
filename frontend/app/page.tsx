"use client";

import { useEffect, useState } from "react";
import {
  apiRequest,
  refreshApiAccessToken,
  setApiAccessToken,
  subscribeToApiAccessToken,
} from "./api";
import AuthScreen from "./auth-screen";
import Dashboard from "./dashboard";

export default function Home() {
  const [token, setToken] = useState<string | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const unsubscribe = subscribeToApiAccessToken(setToken);
    void refreshApiAccessToken().finally(() => setReady(true));
    return unsubscribe;
  }, []);

  function authenticated(nextToken: string) {
    setApiAccessToken(nextToken);
    setToken(nextToken);
  }

  async function logout() {
    try {
      await apiRequest<void>(
        "/api/v1/auth/logout",
        { method: "POST" },
        token ?? undefined,
      );
    } finally {
      setApiAccessToken(null);
      setToken(null);
    }
  }

  if (!ready) return <AuthScreen onAuthenticated={authenticated} />;
  return token ? <Dashboard token={token} onLogout={logout} /> : <AuthScreen onAuthenticated={authenticated} />;
}
