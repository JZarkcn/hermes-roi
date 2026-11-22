// Stub of @hermes/plugin-sdk for the visual smoke test. useQuery is a
// minimal fire-once implementation; the rest are the real constant shapes.
import { useState, useEffect } from "react";

export const ROUTES_AREA = "routes-area";
export const SIDEBAR_NAV_AREA = "sidebar-nav-area";

export function useQuery({ queryFn }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [fetching, setFetching] = useState(true);
  const [nonce, setNonce] = useState(0);
  useEffect(() => {
    let on = true;
    setFetching(true);
    Promise.resolve()
      .then(() => queryFn())
      .then((d) => on && (setData(d), setError(null)))
      .catch((e) => on && setError(e))
      .finally(() => on && (setFetching(false), setLoading(false)));
    return () => { on = false; };
  }, [nonce]);
  return {
    data, error,
    isLoading: loading,
    isFetching: fetching,
    refetch: () => setNonce((n) => n + 1),
  };
}

export function Skeleton() {
  return window.React.createElement("div", { style: { opacity: 0.4, padding: 24 } }, "loading…");
}
