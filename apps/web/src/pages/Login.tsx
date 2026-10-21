import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { z } from "zod";
import { useAuth } from "../auth/AuthProvider";
import { AuthLayout } from "../components/Layout";
import { Alert, BrutalCard, Button, Field, Input } from "../components/ui";
import { $api } from "../lib/api";
import { useErrorMessage } from "../lib/useErrorMessage";
import { zodResolver } from "../lib/zodResolver";

const schema = z.object({
  email: z.email("invalidEmail"),
  password: z.string().min(1, "required"),
});
type Values = z.infer<typeof schema>;

export function LoginPage() {
  const { t } = useTranslation();
  const message = useErrorMessage();
  const { signIn } = useAuth();
  const login = $api.useMutation("post", "/api/v1/auth/login");
  const form = useForm<Values>({ resolver: zodResolver(schema) });
  const { errors } = form.formState;

  const onSubmit = form.handleSubmit(async (values) => {
    const tokens = await login.mutateAsync({ body: { ...values, client: "web" } });
    await signIn(tokens);
  });

  return (
    <AuthLayout>
      <BrutalCard className="space-y-5">
        <h2 className="font-display text-2xl font-extrabold">{t("auth.loginTitle")}</h2>
        <form className="space-y-4" onSubmit={(e) => void onSubmit(e).catch(() => {})} noValidate>
          <Field label={t("auth.email")} error={errors.email && message(errors.email.message)}>
            <Input
              type="email"
              autoComplete="email"
              dir="ltr"
              aria-invalid={!!errors.email}
              {...form.register("email")}
            />
          </Field>
          <Field
            label={t("auth.password")}
            error={errors.password && message(errors.password.message)}
          >
            <Input
              type="password"
              autoComplete="current-password"
              dir="ltr"
              aria-invalid={!!errors.password}
              {...form.register("password")}
            />
          </Field>
          {login.error && <Alert>{message(login.error)}</Alert>}
          <Button type="submit" className="w-full" disabled={login.isPending}>
            {t("auth.submitLogin")}
          </Button>
        </form>
        <p className="text-center text-sm text-ink-soft">
          {t("auth.noAccount")}{" "}
          <Link to="/register" className="font-bold text-accent-strong underline underline-offset-4">
            {t("auth.toRegister")}
          </Link>
        </p>
      </BrutalCard>
    </AuthLayout>
  );
}
