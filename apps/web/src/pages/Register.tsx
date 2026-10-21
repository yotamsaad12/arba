import type { ClientType } from "@arba/shared";
import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { z } from "zod";
import { useAuth } from "../auth/AuthProvider";
import { AuthLayout } from "../components/Layout";
import { Alert, BrutalCard, Button, Field, Input, cx } from "../components/ui";
import { $api } from "../lib/api";
import { useErrorMessage } from "../lib/useErrorMessage";
import { zodResolver } from "../lib/zodResolver";

const schema = z
  .object({
    client_type: z.enum(["private", "business"]),
    name: z.string().trim().min(1, "required"),
    organization_name: z.string().trim().optional(),
    email: z.email("invalidEmail"),
    password: z.string().min(8, "passwordTooShort"),
    phone: z.string().trim().optional(),
  })
  .refine((v) => v.client_type === "private" || !!v.organization_name, {
    path: ["organization_name"],
    message: "required",
  });
type Values = z.infer<typeof schema>;

export function RegisterPage() {
  const { t } = useTranslation();
  const message = useErrorMessage();
  const { signIn } = useAuth();
  const register = $api.useMutation("post", "/api/v1/auth/register");
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { client_type: "private" },
  });
  const { errors } = form.formState;
  const clientType = form.watch("client_type");

  const onSubmit = form.handleSubmit(async ({ phone, organization_name, ...values }) => {
    const tokens = await register.mutateAsync({
      body: {
        ...values,
        phone: phone || null,
        organization_name: values.client_type === "business" ? organization_name : null,
        client: "web",
      },
    });
    await signIn(tokens);
  });

  const options: { value: ClientType; title: string; hint: string }[] = [
    { value: "private", title: t("auth.clientTypePrivate"), hint: t("auth.clientTypePrivateHint") },
    {
      value: "business",
      title: t("auth.clientTypeBusiness"),
      hint: t("auth.clientTypeBusinessHint"),
    },
  ];

  return (
    <AuthLayout>
      <BrutalCard className="space-y-5">
        <h2 className="font-display text-2xl font-extrabold">{t("auth.registerTitle")}</h2>
        <form className="space-y-4" onSubmit={(e) => void onSubmit(e).catch(() => {})} noValidate>
          <fieldset className="space-y-2">
            <legend className="mb-1.5 text-sm font-medium">{t("auth.clientType")}</legend>
            {options.map((o) => (
              <label
                key={o.value}
                className={cx(
                  "flex cursor-pointer gap-3 rounded-xl border-2 p-3 transition-all",
                  clientType === o.value ? "border-ink bg-accent-soft shadow-[3px_3px_0_0_var(--color-ink)]" : "border-line",
                )}
              >
                <input
                  type="radio"
                  value={o.value}
                  className="mt-1 accent-ink"
                  {...form.register("client_type")}
                />
                <span>
                  <span className="block font-medium">{o.title}</span>
                  <span className="block text-sm text-ink-soft">{o.hint}</span>
                </span>
              </label>
            ))}
          </fieldset>

          <Field label={t("auth.name")} error={errors.name && message(errors.name.message)}>
            <Input autoComplete="name" aria-invalid={!!errors.name} {...form.register("name")} />
          </Field>
          {clientType === "business" && (
            <Field
              label={t("auth.organizationName")}
              error={errors.organization_name && message(errors.organization_name.message)}
            >
              <Input
                autoComplete="organization"
                aria-invalid={!!errors.organization_name}
                {...form.register("organization_name")}
              />
            </Field>
          )}
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
            hint={t("auth.passwordHint")}
            error={errors.password && message(errors.password.message)}
          >
            <Input
              type="password"
              autoComplete="new-password"
              dir="ltr"
              aria-invalid={!!errors.password}
              {...form.register("password")}
            />
          </Field>
          <Field label={t("auth.phone")}>
            <Input type="tel" autoComplete="tel" dir="ltr" {...form.register("phone")} />
          </Field>

          {register.error && <Alert>{message(register.error)}</Alert>}
          <Button type="submit" className="w-full" disabled={register.isPending}>
            {t("auth.submitRegister")}
          </Button>
        </form>
        <p className="text-center text-sm text-ink-soft">
          {t("auth.haveAccount")}{" "}
          <Link to="/login" className="font-bold text-accent-strong underline underline-offset-4">
            {t("auth.toLogin")}
          </Link>
        </p>
      </BrutalCard>
    </AuthLayout>
  );
}
