// Stub of @hermes/plugin-sdk for the visual smoke test. useQuery is a
// minimal fire-once implementation; the rest are the real constant shapes.
import { useState, useEffect } from "react";

export const ROUTES_AREA = "routes-area";
export const SIDEBAR_NAV_AREA = "sidebar-nav-area";

export function useQuery({ queryFn }) {
  const [state, setState] = useState({ data: null, isLoading: true, error: null });
  useEffect(() => {
    let on = true;
    Promise.resolve()
      .then(() => queryFn())
      .then((data) => on && setState({ data, isLoading: false, error: null }))
      .catch((error) => on && setState({ data: null, isLoading: false, error }));
    return () => { on = false; };
  }, []);
  return state;
}

export function Skeleton() {
  return window.React.createElement("div", { style: { opacity: 0.4, padding: 24 } }, "loading…");
}
