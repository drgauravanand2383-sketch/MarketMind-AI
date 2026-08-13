import { useEffect, useState } from "react";

/** Delays reflecting `value` until it's stopped changing for `delayMs` —
 * used to avoid firing a new server query on every keystroke in a
 * search/filter input. */
export function useDebouncedValue<T>(value: T, delayMs = 300): T {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const timer = setTimeout(() => {
      setDebounced(value);
    }, delayMs);
    return () => {
      clearTimeout(timer);
    };
  }, [value, delayMs]);

  return debounced;
}
