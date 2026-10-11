import { useEffect, useState } from 'react';
import { pendingKey, type DecisionPayload } from './api/client';

export function usePendingDecision(trialId: string) {
  const [pending, setPending] = useState<DecisionPayload | null>(() => JSON.parse(localStorage.getItem(pendingKey(trialId)) || 'null'));
  useEffect(() => {
    const update = () => setPending(JSON.parse(localStorage.getItem(pendingKey(trialId)) || 'null'));
    window.addEventListener('preference-lab-pending', update);
    window.addEventListener('storage', update);
    return () => {
      window.removeEventListener('preference-lab-pending', update);
      window.removeEventListener('storage', update);
    };
  }, [trialId]);
  return pending;
}
