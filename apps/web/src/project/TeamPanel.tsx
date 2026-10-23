import type { Contact, DocumentRequestInfo, Requirement } from "@arba/api-client";
import { AnimatePresence, motion } from "motion/react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useCelebrate } from "../components/Celebrations";
import { Alert, Badge, Button, Field, Input } from "../components/ui";
import { $api, invalidateProjects } from "../lib/api";
import { formatDateTime } from "../lib/upload";
import { useErrorMessage } from "../lib/useErrorMessage";

type Role = Contact["role"];

// Professionals asked through an upload link. Approving bodies get letters (outreach), and
// the owner is the person using the app.
export const PROFESSIONAL_ROLES: Role[] = [
  "surveyor",
  "architect",
  "structural_engineer",
  "supervising_engineer",
  "soil_consultant",
  "testing_lab",
  "electrical_inspector",
  "gas_installer",
  "plumber",
  "green_building_lab",
  "contractor",
];
export const isProfessional = (role: string): role is Role => (PROFESSIONAL_ROLES as string[]).includes(role);

/** Asking a professional for this step's documents: who, what, and a note. */
export function RequestForm({
  projectId,
  requirement: r,
  onClose,
}: {
  projectId: string;
  requirement: Requirement;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const message = useErrorMessage();
  const { toast } = useCelebrate();
  const contacts = $api.useQuery("get", "/api/v1/projects/{project_id}/contacts", {
    params: { path: { project_id: projectId } },
  });
  const create = $api.useMutation("post", "/api/v1/projects/{project_id}/document-requests");
  const sameRole = (contacts.data ?? []).filter((c) => c.role === r.authority_type);
  const [contactId, setContactId] = useState<string | "new" | null>(null);
  const chosen = contactId ?? (sameRole[0]?.id ?? "new");
  const [person, setPerson] = useState({ name: "", email: "", phone: "" });
  const [docs, setDocs] = useState<string[]>(r.required_documents.length ? r.required_documents : [r.title]);
  const [extra, setExtra] = useState("");
  const [note, setNote] = useState("");
  const role = isProfessional(r.authority_type) ? r.authority_type : "contractor";

  const submit = () => {
    const all = [...docs, ...(extra.trim() ? [extra.trim()] : [])];
    create.mutate(
      {
        params: { path: { project_id: projectId } },
        body: {
          requirement_id: r.id,
          documents: all,
          note: note.trim() || null,
          ...(chosen === "new"
            ? { contact: { role, name: person.name, email: person.email || null, phone: person.phone || null } }
            : { contact_id: chosen }),
        },
      },
      {
        onSuccess: (sent) => {
          void invalidateProjects();
          if (sent.sent_by.length) {
            const channels = sent.sent_by.map((c) => t(`requests.channel.${c as "email" | "whatsapp"}`)).join(" ו");
            toast(t("requests.sentVia", { name: sent.contact.name, channels }), "📨");
          } else {
            void navigator.clipboard?.writeText(sent.link);
            toast(t("requests.notSent"), "🔗");
          }
          onClose();
        },
      },
    );
  };

  return (
    <motion.div
      initial={{ opacity: 0, height: 0 }}
      animate={{ opacity: 1, height: "auto" }}
      exit={{ opacity: 0, height: 0 }}
      className="space-y-3 overflow-hidden rounded-xl border-2 border-ink bg-bg p-3"
    >
      <div className="text-sm font-bold">{t("requests.who")}</div>
      <div className="flex flex-wrap gap-2">
        {sameRole.map((c) => (
          <Chip key={c.id} active={chosen === c.id} onClick={() => setContactId(c.id)}>
            👷 {c.name}
          </Chip>
        ))}
        <Chip active={chosen === "new"} onClick={() => setContactId("new")}>
          {t("requests.newPerson")}
        </Chip>
      </div>
      {chosen === "new" && (
        <div className="grid gap-2 sm:grid-cols-3">
          <Input
            placeholder={`${t("team.name")} (${t(`authority.${role}`)})`}
            value={person.name}
            onChange={(e) => setPerson({ ...person, name: e.target.value })}
          />
          <Input
            dir="ltr"
            type="email"
            placeholder={t("team.email")}
            value={person.email}
            onChange={(e) => setPerson({ ...person, email: e.target.value })}
          />
          <Input
            dir="ltr"
            inputMode="tel"
            placeholder={t("team.phone")}
            value={person.phone}
            onChange={(e) => setPerson({ ...person, phone: e.target.value })}
          />
        </div>
      )}

      <div className="text-sm font-bold">{t("requests.which")}</div>
      <div className="flex flex-wrap gap-2">
        {(r.required_documents.length ? r.required_documents : [r.title]).map((d) => (
          <Chip
            key={d}
            active={docs.includes(d)}
            onClick={() => setDocs(docs.includes(d) ? docs.filter((x) => x !== d) : [...docs, d])}
          >
            {docs.includes(d) ? "✓ " : ""}
            {d}
          </Chip>
        ))}
      </div>
      <Input placeholder={t("requests.addDoc")} value={extra} onChange={(e) => setExtra(e.target.value)} />
      <Input placeholder={t("requests.notePlaceholder")} value={note} onChange={(e) => setNote(e.target.value)} />
      {create.isError && <Alert>{message(create.error)}</Alert>}
      <div className="flex gap-2">
        <Button
          size="sm"
          disabled={
            create.isPending ||
            (docs.length === 0 && !extra.trim()) ||
            (chosen === "new" && (!person.name.trim() || (!person.email && !person.phone)))
          }
          onClick={submit}
        >
          📨 {create.isPending ? t("requests.sending") : t("requests.send")}
        </Button>
        <Button size="sm" variant="ghost" onClick={onClose}>
          {t("requests.close")}
        </Button>
      </div>
    </motion.div>
  );
}

function Chip({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <motion.button
      type="button"
      whileTap={{ scale: 0.94 }}
      onClick={onClick}
      className={
        active
          ? "rounded-full border-2 border-ink bg-accent px-3 py-1 text-sm font-bold"
          : "rounded-full border-2 border-line bg-surface px-3 py-1 text-sm hover:border-ink"
      }
    >
      {children}
    </motion.button>
  );
}

/** Requests waiting on professionals, with what they uploaded so far. */
export function RequestsPanel({ projectId, canEdit }: { projectId: string; canEdit: boolean }) {
  const { t } = useTranslation();
  const requests = $api.useQuery("get", "/api/v1/projects/{project_id}/document-requests", {
    params: { path: { project_id: projectId } },
  });
  const list = requests.data ?? [];
  if (list.length === 0) return null;
  return (
    <section className="space-y-3">
      <h2 className="flex items-center gap-2 font-display text-xl font-extrabold">
        <motion.span animate={{ y: [0, -3, 0] }} transition={{ duration: 1.6, repeat: Infinity }}>
          📥
        </motion.span>
        {t("requests.title")}
      </h2>
      <div className="grid gap-3 md:grid-cols-2">
        <AnimatePresence initial={false}>
          {list.map((r) => (
            <RequestCard key={r.id} projectId={projectId} request={r} canEdit={canEdit} />
          ))}
        </AnimatePresence>
      </div>
    </section>
  );
}

function RequestCard({
  projectId,
  request: r,
  canEdit,
}: {
  projectId: string;
  request: DocumentRequestInfo;
  canEdit: boolean;
}) {
  const { t } = useTranslation();
  const { toast } = useCelebrate();
  const params = { params: { path: { project_id: projectId, request_id: r.id } } };
  const after = { onSuccess: () => void invalidateProjects() };
  const resend = $api.useMutation("post", "/api/v1/projects/{project_id}/document-requests/{request_id}/resend", after);
  const cancel = $api.useMutation("post", "/api/v1/projects/{project_id}/document-requests/{request_id}/cancel", after);
  const tone = r.status === "fulfilled" ? "success" : "warning";
  return (
    <motion.article
      layout
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.95 }}
      className="space-y-2 rounded-2xl border-2 border-ink bg-surface p-4"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="text-xs text-ink-soft">{t(`authority.${r.contact.role}`)}</div>
          <div className="font-bold">👷 {r.contact.name}</div>
          <div className="text-sm text-ink-soft">{r.requirement_title}</div>
        </div>
        <Badge tone={tone}>{t(`requests.status.${r.status}`)}</Badge>
      </div>
      <div className="flex flex-wrap gap-1">
        {r.documents.map((d) => (
          <span key={d} className="rounded-full bg-bg px-2 py-0.5 text-xs">
            {d}
          </span>
        ))}
      </div>
      <div className="text-sm">
        {r.files.length ? `📎 ${t("requests.files", { count: r.files.length })}` : t("requests.noFiles")}
        {r.last_sent_at && (
          <span className="text-ink-soft"> · {t("requests.lastSent", { when: formatDateTime(r.last_sent_at) })}</span>
        )}
      </div>
      {canEdit && r.status === "open" && (
        <div className="flex flex-wrap gap-2">
          <Button
            size="sm"
            variant="secondary"
            disabled={resend.isPending}
            onClick={() => resend.mutate(params, { onSuccess: () => toast(t("requests.resent"), "📨") })}
          >
            {t("requests.resend")}
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => {
              void navigator.clipboard?.writeText(r.link);
              toast(t("requests.copied"), "🔗");
            }}
          >
            🔗 {t("requests.copyLink")}
          </Button>
          <Button size="sm" variant="ghost" disabled={cancel.isPending} onClick={() => cancel.mutate(params)}>
            {t("requests.cancel")}
          </Button>
        </div>
      )}
    </motion.article>
  );
}

/** The professionals on the project. They're added as requests go out, or by hand here. */
export function TeamPanel({ projectId, canEdit }: { projectId: string; canEdit: boolean }) {
  const { t } = useTranslation();
  const message = useErrorMessage();
  const path = { params: { path: { project_id: projectId } } };
  const contacts = $api.useQuery("get", "/api/v1/projects/{project_id}/contacts", path);
  const add = $api.useMutation("post", "/api/v1/projects/{project_id}/contacts", {
    onSuccess: () => void invalidateProjects(),
  });
  const remove = $api.useMutation("delete", "/api/v1/projects/{project_id}/contacts/{contact_id}", {
    onSuccess: () => void invalidateProjects(),
  });
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState<{ role: Role; name: string; email: string; phone: string }>({
    role: "surveyor",
    name: "",
    email: "",
    phone: "",
  });
  const list = contacts.data ?? [];

  return (
    <section className="space-y-3">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h2 className="font-display text-xl font-extrabold">👷 {t("team.title")}</h2>
          <p className="text-sm text-ink-soft">{t("team.hint")}</p>
        </div>
        {canEdit && !adding && (
          <Button size="sm" variant="secondary" onClick={() => setAdding(true)}>
            {t("requests.newPerson")}
          </Button>
        )}
      </div>
      {list.length === 0 && !adding && <p className="text-sm text-ink-soft">{t("team.empty")}</p>}
      <AnimatePresence>
        {adding && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            className="grid gap-2 overflow-hidden rounded-xl border-2 border-ink bg-surface p-3 sm:grid-cols-2"
          >
            <Field label={t("team.role")}>
              <select
                value={form.role}
                onChange={(e) => setForm({ ...form, role: e.target.value as Role })}
                className="min-h-12 w-full rounded-xl border-2 border-line bg-surface px-3"
              >
                {PROFESSIONAL_ROLES.map((role) => (
                  <option key={role} value={role}>
                    {t(`authority.${role}`)}
                  </option>
                ))}
              </select>
            </Field>
            <Field label={t("team.name")}>
              <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            </Field>
            <Field label={t("team.email")} hint={t("team.contactHint")}>
              <Input dir="ltr" type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
            </Field>
            <Field label={t("team.phone")}>
              <Input dir="ltr" inputMode="tel" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
            </Field>
            {add.isError && <Alert>{message(add.error)}</Alert>}
            <div className="flex gap-2 sm:col-span-2">
              <Button
                size="sm"
                disabled={add.isPending || !form.name.trim() || (!form.email && !form.phone)}
                onClick={() =>
                  add.mutate(
                    {
                      ...path,
                      body: { role: form.role, name: form.name, email: form.email || null, phone: form.phone || null },
                    },
                    {
                      onSuccess: () => {
                        setAdding(false);
                        setForm({ role: "surveyor", name: "", email: "", phone: "" });
                      },
                    },
                  )
                }
              >
                ✓ {t("permit.save")}
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setAdding(false)}>
                {t("requests.close")}
              </Button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {list.map((c, i) => (
          <motion.div
            key={c.id}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.04 }}
            className="flex items-start gap-3 rounded-xl border-2 border-line bg-surface p-3"
          >
            <span className="text-2xl">👷</span>
            <div className="min-w-0 flex-1">
              <div className="text-xs text-ink-soft">{t(`authority.${c.role}`)}</div>
              <div className="font-bold">{c.name}</div>
              <div dir="ltr" className="truncate text-end text-xs text-ink-soft">
                {[c.email, c.phone].filter(Boolean).join(" · ")}
              </div>
            </div>
            {canEdit && (
              <button
                type="button"
                className="text-xs text-ink-soft hover:text-danger"
                onClick={() => remove.mutate({ params: { path: { project_id: projectId, contact_id: c.id } } })}
              >
                {t("team.remove")}
              </button>
            )}
          </motion.div>
        ))}
      </div>
    </section>
  );
}
