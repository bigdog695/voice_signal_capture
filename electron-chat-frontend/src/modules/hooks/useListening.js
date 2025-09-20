// Replaced by ListeningProvider context. Provide same signature for callers.
import { useListeningContext } from '../listening/ListeningProvider';

export function useListening() {
  return useListeningContext();
}
