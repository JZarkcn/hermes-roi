// Harness: single-React-instance shims over the local UMD builds.
// The import map maps "react" / "react-dom/client" to these, so the plugin
// and the SDK stub share ONE React instance (hooks need that).
export const createElement = window.React.createElement;
export const useState = window.React.useState;
export const useEffect = window.React.useEffect;
export default window.React;
