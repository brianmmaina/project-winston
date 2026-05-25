/**
 * Polls a backend job (`GET /api/jobs/{id}`) until it reaches a terminal state
 * (completed / failed / cancelled). Returns the latest status, plus a small
 * helper to start polling a fresh job_id.
 *
 * Usage:
 *
 *   const { job, isPolling, error, start, reset } = useJob();
 *   const onClick = async () => {
 *     const r = await triggerStockRefresh();
 *     start(r.job_id);
 *   };
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { ApiClientError, getJob } from "../api/client";
import type { JobStatus } from "../api/types.generated";

export interface UseJobResult {
  job: JobStatus | null;
  isPolling: boolean;
  error: string | null;
  start: (jobId: string) => void;
  reset: () => void;
}

const DEFAULT_INTERVAL_MS = 1500;

export function useJob(intervalMs: number = DEFAULT_INTERVAL_MS): UseJobResult {
  const [job, setJob] = useState<JobStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isPolling, setIsPolling] = useState<boolean>(false);
  const timerRef = useRef<number | null>(null);
  const cancelledRef = useRef<boolean>(false);

  const stopTimer = () => {
    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  };

  const reset = useCallback(() => {
    cancelledRef.current = true;
    stopTimer();
    setJob(null);
    setError(null);
    setIsPolling(false);
  }, []);

  const start = useCallback(
    (jobId: string) => {
      cancelledRef.current = false;
      setError(null);
      setIsPolling(true);
      const tick = async () => {
        if (cancelledRef.current) return;
        try {
          const next = await getJob(jobId);
          setJob(next);
          if (next.is_terminal) {
            setIsPolling(false);
            return;
          }
          timerRef.current = window.setTimeout(tick, intervalMs);
        } catch (e) {
          const msg = e instanceof ApiClientError ? e.message : "Polling failed.";
          setError(msg);
          setIsPolling(false);
        }
      };
      void tick();
    },
    [intervalMs],
  );

  useEffect(() => {
    return () => {
      cancelledRef.current = true;
      stopTimer();
    };
  }, []);

  return { job, isPolling, error, start, reset };
}
