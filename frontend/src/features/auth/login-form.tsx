import type { ReactNode } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useNavigate } from "@tanstack/react-router";
import { FormField } from "@/components/forms/form-field";
import { LoadingButton } from "@/components/forms/loading-button";
import { useLogin } from "@/hooks/use-auth";
import { ApiError } from "@/services/api/errors";

const loginSchema = z.object({
  username: z.string().min(1, "Username is required"),
  password: z.string().min(1, "Password is required"),
  rememberMe: z.boolean(),
});

type LoginFormValues = z.infer<typeof loginSchema>;

export function LoginForm({ redirectTo = "/" }: { redirectTo?: string }): ReactNode {
  const login = useLogin();
  const navigate = useNavigate();
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<LoginFormValues>({ resolver: zodResolver(loginSchema), defaultValues: { rememberMe: true } });

  const onSubmit = handleSubmit(({ username, password, rememberMe }) => {
    login.mutate(
      { username, password, rememberMe },
      {
        onSuccess: () => {
          void navigate({ to: redirectTo });
        },
      },
    );
  });

  return (
    <form onSubmit={(event) => void onSubmit(event)} className="flex w-full max-w-sm flex-col gap-4" noValidate>
      <FormField label="Username" type="text" autoComplete="username" error={errors.username?.message} {...register("username")} />
      <FormField
        label="Password"
        type="password"
        autoComplete="current-password"
        error={errors.password?.message}
        {...register("password")}
      />

      <label className="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-300">
        <input type="checkbox" className="h-4 w-4 rounded border-slate-300 dark:border-slate-700" {...register("rememberMe")} />
        Remember me on this device
      </label>

      {login.isError && (
        <p role="alert" className="text-sm text-red-600 dark:text-red-400">
          {login.error instanceof ApiError && login.error.isAuthError
            ? "Incorrect username or password."
            : "Login failed. Please try again."}
        </p>
      )}

      <LoadingButton type="submit" isLoading={login.isPending} loadingText="Signing in…">
        Sign in
      </LoadingButton>
    </form>
  );
}
