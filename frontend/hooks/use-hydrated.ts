import { useSyncExternalStore } from "react";

/** Never fires: whether we are hydrated cannot change again after hydration. */
const subscribe = () => () => {};

/**
 * `false` during server render and the hydrating render, `true` afterwards.
 *
 * The usual `useState(false)` + `useEffect(() => setMounted(true))` does the
 * same job, but React 19 flags setting state directly in an effect because it
 * causes a cascading render. `useSyncExternalStore` expresses the same idea as
 * a value that simply differs between the server and client snapshots.
 */
export function useHydrated(): boolean {
  return useSyncExternalStore(
    subscribe,
    () => true,
    () => false,
  );
}
