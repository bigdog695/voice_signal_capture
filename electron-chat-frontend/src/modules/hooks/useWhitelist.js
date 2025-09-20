// Whitelist feature removed: this hook is now a no-op.
// We still memoize returned functions/object to keep stable references
// so that effects depending on them don't re-run unnecessarily.
import { useCallback, useMemo } from 'react';

export function useWhitelist() {
  const registerToWhitelist = useCallback(async () => true, []);
  const ensureWhitelisted = useCallback(async () => true, []);
  const isRegistered = useCallback(() => true, []);

  return useMemo(() => ({ registerToWhitelist, ensureWhitelisted, isRegistered }), [registerToWhitelist, ensureWhitelisted, isRegistered]);
}