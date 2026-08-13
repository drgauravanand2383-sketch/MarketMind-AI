import type { ReactNode } from "react";
import { createFileRoute, redirect } from "@tanstack/react-router";
import { LoginForm } from "@/features/auth/login-form";
import { redirectSearchSchema } from "@/lib/route-search";
import { useAuthStore } from "@/store/auth-store";

export const Route = createFileRoute("/login")({
  validateSearch: redirectSearchSchema,
  beforeLoad: () => {
    if (useAuthStore.getState().status === "authenticated") {
      throw redirect({ to: "/" });
    }
  },
  component: LoginPage,
});

function LoginPage(): ReactNode {
  const { redirect: redirectTo } = Route.useSearch();

  return (
    <div className="flex min-h-screen items-center justify-center p-6">
      <div className="flex w-full max-w-sm flex-col gap-6">
        <h1 className="text-center text-xl font-semibold text-slate-900 dark:text-slate-100">
          Sign in to MarketMind AI
        </h1>
        <LoginForm redirectTo={redirectTo ?? "/"} />
      </div>
    </div>
  );
}
