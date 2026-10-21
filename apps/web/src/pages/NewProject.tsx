import { useEffect } from "react";
import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router";
import { z } from "zod";
import { Alert, Button, Card, Field, Input, Spinner, cx } from "../components/ui";
import { $api, invalidateProjects } from "../lib/api";
import { useErrorMessage } from "../lib/useErrorMessage";
import { zodResolver } from "../lib/zodResolver";

const schema = z.object({
  name: z.string().trim().min(1, "required"),
  template_id: z.string().min(1, "required"),
  municipality: z.string().trim().min(1, "required"),
  address: z.string().trim(),
  floors: z.number("required").int().min(1, "required").max(60),
  gush: z.string().trim(),
  helka: z.string().trim(),
  permit_number: z.string().trim(),
});
type Values = z.infer<typeof schema>;

export function NewProjectPage() {
  const { t } = useTranslation();
  const message = useErrorMessage();
  const navigate = useNavigate();
  const templates = $api.useQuery("get", "/api/v1/templates");
  const create = $api.useMutation("post", "/api/v1/projects");
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { floors: 1, address: "", gush: "", helka: "", permit_number: "" },
  });
  const { errors } = form.formState;
  const selectedTemplate = form.watch("template_id");

  // Preselect when there is only one template to pick from.
  useEffect(() => {
    const only = templates.data?.length === 1 ? templates.data[0] : undefined;
    if (only && !form.getValues("template_id")) form.setValue("template_id", only.id);
  }, [templates.data, form]);

  const onSubmit = form.handleSubmit(async ({ address, gush, helka, permit_number, ...values }) => {
    const project = await create.mutateAsync({
      body: {
        ...values,
        address: address || null,
        gush: gush || null,
        helka: helka || null,
        permit_number: permit_number || null,
      },
    });
    await invalidateProjects();
    void navigate(`/projects/${project.id}`);
  });

  if (templates.isPending) return <Spinner label={t("app.loading")} />;

  const field = (name: keyof Values) => ({
    "aria-invalid": !!errors[name],
    ...form.register(name, name === "floors" ? { valueAsNumber: true } : undefined),
  });
  const error = (name: keyof Values) => errors[name] && message(errors[name]?.message);

  return (
    <div className="space-y-5">
      <Link to="/" className="text-sm text-brand">
        → {t("app.back")}
      </Link>
      <h1 className="text-2xl font-bold">{t("projects.newTitle")}</h1>

      <form className="space-y-5" onSubmit={(e) => void onSubmit(e).catch(() => {})} noValidate>
        <Card className="space-y-4">
          <Field label={t("projects.name")} error={error("name")}>
            <Input placeholder={t("projects.namePlaceholder")} {...field("name")} />
          </Field>
          <Field label={t("projects.municipality")} error={error("municipality")}>
            <Input placeholder={t("projects.municipalityPlaceholder")} {...field("municipality")} />
          </Field>
          <Field label={t("projects.address")}>
            <Input autoComplete="street-address" {...field("address")} />
          </Field>
          <Field label={t("projects.floors")} hint={t("projects.floorsHint")} error={error("floors")}>
            <Input type="number" inputMode="numeric" min={1} max={60} {...field("floors")} />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label={t("projects.gush")}>
              <Input inputMode="numeric" {...field("gush")} />
            </Field>
            <Field label={t("projects.helka")}>
              <Input inputMode="numeric" {...field("helka")} />
            </Field>
          </div>
          <Field label={t("projects.permitNumber")}>
            <Input {...field("permit_number")} />
          </Field>
        </Card>

        <fieldset className="space-y-2">
          <legend className="mb-1.5 text-sm font-medium">{t("projects.template")}</legend>
          {templates.data?.map((tpl) => (
            <label
              key={tpl.id}
              className={cx(
                "flex cursor-pointer gap-3 rounded-xl border bg-surface p-4",
                selectedTemplate === tpl.id ? "border-brand bg-brand-soft" : "border-line",
              )}
            >
              <input
                type="radio"
                value={tpl.id}
                className="mt-1 accent-brand"
                {...form.register("template_id")}
              />
              <span>
                <span className="block font-medium">{tpl.name}</span>
                <span className="block text-sm text-ink-soft">{tpl.description}</span>
                <span className="block text-xs text-ink-soft">
                  {t("projects.templateRequirements", { count: tpl.requirement_count })}
                </span>
              </span>
            </label>
          ))}
          {errors.template_id && <Alert>{message(errors.template_id.message)}</Alert>}
        </fieldset>

        {create.error && <Alert>{message(create.error)}</Alert>}
        <Button type="submit" className="w-full" disabled={create.isPending}>
          {t("projects.create")}
        </Button>
      </form>
    </div>
  );
}
