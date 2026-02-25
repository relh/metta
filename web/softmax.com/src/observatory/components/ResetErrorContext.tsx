"use client";
import { useRouter } from "next/navigation";
import {
  createContext,
  FC,
  PropsWithChildren,
  use,
  useCallback,
  useEffect,
  useRef,
  useTransition,
} from "react";

type ResetErrorContextValue = {
  resetError: () => void;
  clearError: () => void;
  isPending: boolean;
  registerErrorReset: (reset: () => void) => void;
  unregisterErrorReset: () => void;
};

const ResetErrorContext = createContext<ResetErrorContextValue | null>(null);

export const ResetErrorProvider: FC<PropsWithChildren> = ({ children }) => {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();
  // Single ref is fine: only one error boundary is visible at a time in a linear route tree.
  // If we add parallel routes (@folder slots), upgrade to a Set<() => void>.
  const errorResetRef = useRef<(() => void) | null>(null);

  const registerErrorReset = useCallback((reset: () => void) => {
    errorResetRef.current = reset;
  }, []);

  const unregisterErrorReset = useCallback(() => {
    errorResetRef.current = null;
  }, []);

  const clearError = useCallback(() => {
    startTransition(() => {
      errorResetRef.current?.();
    });
  }, []);

  const resetError = useCallback(() => {
    startTransition(() => {
      errorResetRef.current?.();
      router.refresh();
    });
  }, [router]);

  return (
    <ResetErrorContext
      value={{
        resetError,
        clearError,
        isPending,
        registerErrorReset,
        unregisterErrorReset,
      }}
    >
      {children}
    </ResetErrorContext>
  );
};

export function useResetError() {
  const context = use(ResetErrorContext);
  return context?.resetError;
}

export function useClearError() {
  const context = use(ResetErrorContext);
  return context?.clearError;
}

export function useRegisterErrorReset(reset: () => void) {
  const context = use(ResetErrorContext);
  useEffect(() => {
    context?.registerErrorReset(reset);
    return () => context?.unregisterErrorReset();
  }, [context, reset]);
}
