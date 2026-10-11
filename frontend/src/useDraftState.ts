import { useState } from 'react';
import type { SetStateAction } from 'react';

// Trial-scoped drafts survive refresh; every edit is saved synchronously.
export function useDraftState<T>(trialId: string, field: string, initial: T) {
  const key = `preference_lab_draft_${trialId}_${field}`;
  const [value, setValue] = useState<T>(() => {
    const saved = localStorage.getItem(key);
    if (saved === null) localStorage.setItem(key, JSON.stringify(initial));
    return saved === null ? initial : JSON.parse(saved);
  });
  const update = (next: SetStateAction<T>) => setValue(previous => {
    const result = typeof next === 'function' ? (next as (p: T) => T)(previous) : next;
    localStorage.setItem(key, JSON.stringify(result));
    return result;
  });
  return [value, update] as const;
}
