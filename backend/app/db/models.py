import uuid
from datetime import date, datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import (
    AuthorityType,
    Channel,
    CheckVerdict,
    ClientType,
    ConditionStatus,
    ConditionTiming,
    ContactSource,
    DeliveryChannel,
    DeliveryStatus,
    DependencyKind,
    DocumentSource,
    DocumentStatus,
    DraftKind,
    DraftStatus,
    InboundStatus,
    MailboxProvider,
    MessageDirection,
    MessageKind,
    NotificationKind,
    OrgRole,
    PermitStatus,
    ProjectRole,
    ProjectStatus,
    Repeat,
    RequestStatus,
    RequirementOrigin,
    RequirementStatus,
    ScanStatus,
    SuggestionStatus,
    Urgency,
)
from app.db.base import Base, IdMixin, TimestampMixin

# --- Identity -------------------------------------------------------------------------


class Organization(IdMixin, TimestampMixin, Base):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(sa.String(200))
    type: Mapped[ClientType]


class User(IdMixin, TimestampMixin, Base):
    __tablename__ = "users"

    name: Mapped[str] = mapped_column(sa.String(200))
    email: Mapped[str] = mapped_column(sa.String(320), unique=True)
    phone: Mapped[str | None] = mapped_column(sa.String(32))
    password_hash: Mapped[str] = mapped_column(sa.String(255))

    # Notification preferences.
    notify_email: Mapped[bool] = mapped_column(default=True, server_default=sa.true())
    notify_whatsapp: Mapped[bool] = mapped_column(default=True, server_default=sa.true())
    quiet_nights: Mapped[bool] = mapped_column(default=True, server_default=sa.true())
    quiet_shabbat: Mapped[bool] = mapped_column(default=True, server_default=sa.true())
    # Local hour (Israel time) for the morning summary.
    digest_hour: Mapped[int] = mapped_column(default=7, server_default="7")

    # WhatsApp: set only after the person confirmed a code sent to this number.
    whatsapp_phone: Mapped[str | None] = mapped_column(sa.String(20), unique=True)
    whatsapp_verified_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    whatsapp_opted_out_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    # Last message they sent us. Within 24 hours free-form replies are allowed.
    whatsapp_last_inbound_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))

    @property
    def whatsapp_active(self) -> bool:
        return bool(
            self.whatsapp_phone and self.whatsapp_verified_at and not self.whatsapp_opted_out_at
        )


class Membership(TimestampMixin, Base):
    __tablename__ = "memberships"

    user_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[OrgRole]

    organization: Mapped[Organization] = relationship(lazy="joined")


class RefreshToken(IdMixin, Base):
    __tablename__ = "refresh_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(sa.String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    # Replaced by a newer token. Still accepted for a few seconds (see REFRESH_REUSE_GRACE).
    rotated_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    # Logged out or suspected stolen. Never accepted again.
    revoked_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )


# --- Templates ------------------------------------------------------------------------


class Template(IdMixin, TimestampMixin, Base):
    __tablename__ = "templates"
    __table_args__ = (sa.UniqueConstraint("key", "version", name="key_version"),)

    key: Mapped[str] = mapped_column(sa.String(64))
    version: Mapped[int]
    name: Mapped[str] = mapped_column(sa.String(200))
    description: Mapped[str | None] = mapped_column(sa.Text)
    client_type: Mapped[ClientType]
    building_type: Mapped[str] = mapped_column(sa.String(64))
    municipality: Mapped[str | None] = mapped_column(sa.String(200))
    # [{"key": "...", "title": "...", "description": "..."}] in display order.
    stages: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)

    requirements: Mapped[list["TemplateRequirement"]] = relationship(
        back_populates="template", order_by="TemplateRequirement.order"
    )
    dependencies: Mapped[list["TemplateDependency"]] = relationship()


class TemplateRequirement(IdMixin, Base):
    __tablename__ = "template_requirements"
    __table_args__ = (sa.UniqueConstraint("template_id", "key", name="template_key"),)

    template_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("templates.id", ondelete="CASCADE"), index=True
    )
    key: Mapped[str] = mapped_column(sa.String(64))
    stage: Mapped[str] = mapped_column(sa.String(64))
    title: Mapped[str] = mapped_column(sa.String(300))
    description: Mapped[str | None] = mapped_column(sa.Text)
    authority_type: Mapped[AuthorityType]
    channel: Mapped[Channel]
    estimated_days: Mapped[int] = mapped_column(default=1)
    repeat: Mapped[Repeat] = mapped_column(default=Repeat.none)
    required_documents: Mapped[list[str]] = mapped_column(JSONB, default=list)
    optional: Mapped[bool] = mapped_column(default=False)
    is_form4_gate: Mapped[bool] = mapped_column(default=False)
    order: Mapped[int]

    template: Mapped[Template] = relationship(back_populates="requirements")


class TemplateDependency(Base):
    __tablename__ = "template_dependencies"

    template_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("templates.id", ondelete="CASCADE"), index=True
    )
    requirement_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("template_requirements.id", ondelete="CASCADE"), primary_key=True
    )
    depends_on_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("template_requirements.id", ondelete="CASCADE"), primary_key=True
    )
    kind: Mapped[DependencyKind] = mapped_column(primary_key=True, default=DependencyKind.same)


# --- Projects -------------------------------------------------------------------------


class Project(IdMixin, TimestampMixin, Base):
    __tablename__ = "projects"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    template_id: Mapped[uuid.UUID | None] = mapped_column(sa.ForeignKey("templates.id"))
    name: Mapped[str] = mapped_column(sa.String(200))
    slug: Mapped[str] = mapped_column(sa.String(64), unique=True)
    address: Mapped[str | None] = mapped_column(sa.String(300))
    municipality: Mapped[str] = mapped_column(sa.String(200))
    building_type: Mapped[str] = mapped_column(sa.String(64))
    client_type: Mapped[ClientType]
    floors: Mapped[int] = mapped_column(default=1)
    gush: Mapped[str | None] = mapped_column(sa.String(32))
    helka: Mapped[str | None] = mapped_column(sa.String(32))
    permit_number: Mapped[str | None] = mapped_column(sa.String(64))
    permit_valid_until: Mapped[date | None]
    inbox_address: Mapped[str] = mapped_column(sa.String(320), unique=True)
    status: Mapped[ProjectStatus] = mapped_column(default=ProjectStatus.active)

    # Where it is, in official codes: drives which committee, water corporation etc. apply.
    locality_code: Mapped[int | None] = mapped_column(sa.ForeignKey("localities.code"))
    municipality_code: Mapped[int | None] = mapped_column(sa.ForeignKey("municipalities.code"))
    committee_code: Mapped[str | None] = mapped_column(sa.ForeignKey("planning_committees.code"))

    # Building permit: a project opens without it, but stays "pending" until it checks out.
    permit_status: Mapped[PermitStatus] = mapped_column(
        default=PermitStatus.pending_verification,
        server_default=PermitStatus.pending_verification.value,
    )
    permit_request_number: Mapped[str | None] = mapped_column(sa.String(64))
    permit_issue_date: Mapped[date | None]
    # The committee as written on the permit, compared with the official one for the address.
    permit_committee: Mapped[str | None] = mapped_column(sa.String(200))
    # [{"check": "...", "ok": bool, "message": "..."}]
    permit_checks: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default="[]"
    )
    permit_confirmed_by: Mapped[uuid.UUID | None] = mapped_column(sa.ForeignKey("users.id"))
    permit_confirmed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    # Reading the permit's conditions: null (not yet), reading, ready, failed.
    conditions_status: Mapped[str | None] = mapped_column(sa.String(16))

    template: Mapped[Template | None] = relationship()


class ProjectMember(TimestampMixin, Base):
    __tablename__ = "project_members"

    project_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[ProjectRole]


class Authority(IdMixin, TimestampMixin, Base):
    """An approving body: a planning committee, a water corporation, a fire district…"""

    __tablename__ = "authorities"
    __table_args__ = (sa.UniqueConstraint("type", "name", name="type_name"),)

    type: Mapped[AuthorityType]
    name: Mapped[str] = mapped_column(sa.String(200))
    website: Mapped[str | None] = mapped_column(sa.String(300))
    # Public search for permit requests, where the committee has one.
    permit_search_url: Mapped[str | None] = mapped_column(sa.String(500))
    # Set for planning committees: the official planning-area code.
    committee_code: Mapped[str | None] = mapped_column(
        sa.ForeignKey("planning_committees.code"), unique=True
    )
    # Bodies that serve the whole country (e.g. Home Front Command) have no areas.
    national: Mapped[bool] = mapped_column(default=False, server_default=sa.false())
    notes: Mapped[str | None] = mapped_column(sa.Text)


class AuthorityArea(Base):
    """Which local authorities a body serves."""

    __tablename__ = "authority_areas"

    authority_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("authorities.id", ondelete="CASCADE"), primary_key=True
    )
    municipality_code: Mapped[int] = mapped_column(
        sa.ForeignKey("municipalities.code"), primary_key=True, index=True
    )


class AuthorityContact(IdMixin, TimestampMixin, Base):
    """A way to reach a body for a purpose, with where it came from and when it was checked."""

    __tablename__ = "authority_contacts"

    authority_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("authorities.id", ondelete="CASCADE"), index=True
    )
    # e.g. "רישוי בנייה", "טופס 4", "חיבור מים"
    purpose: Mapped[str] = mapped_column(sa.String(100))
    channel: Mapped[Channel]
    email: Mapped[str | None] = mapped_column(sa.String(320), index=True)
    phone: Mapped[str | None] = mapped_column(sa.String(32))
    url: Mapped[str | None] = mapped_column(sa.String(500))
    source: Mapped[ContactSource]
    source_url: Mapped[str | None] = mapped_column(sa.String(500))
    verified_at: Mapped[date | None]
    # Project the contact was learned from, if any.
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("projects.id", ondelete="SET NULL")
    )
    notes: Mapped[str | None] = mapped_column(sa.Text)


# --- Official reference data (see app/scripts/sync_reference_data.py) ------------------


class PlanningCommittee(Base):
    __tablename__ = "planning_committees"

    code: Mapped[str] = mapped_column(sa.String(16), primary_key=True)
    name: Mapped[str] = mapped_column(sa.String(200))
    # מקומי / מרחבי / גלילי / מיוחד
    kind: Mapped[str] = mapped_column(sa.String(32))
    district: Mapped[str] = mapped_column(sa.String(64))


class Municipality(Base):
    """A local authority: city, local council or regional council."""

    __tablename__ = "municipalities"

    code: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(sa.String(200), index=True)
    long_name: Mapped[str] = mapped_column(sa.String(200))
    kind: Mapped[str] = mapped_column(sa.String(32))
    district: Mapped[str] = mapped_column(sa.String(64))
    committee_code: Mapped[str | None] = mapped_column(sa.ForeignKey("planning_committees.code"))
    # "planning_map" when the official map says so; "assumed" when we take the authority to be
    # its own committee because the map doesn't list it.
    committee_source: Mapped[str | None] = mapped_column(sa.String(16))


class Locality(Base):
    __tablename__ = "localities"

    code: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(sa.String(200), index=True)
    name_en: Mapped[str | None] = mapped_column(sa.String(200))
    municipality_code: Mapped[int | None] = mapped_column(sa.ForeignKey("municipalities.code"))


class Requirement(IdMixin, TimestampMixin, Base):
    __tablename__ = "requirements"

    project_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    template_requirement_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("template_requirements.id", ondelete="SET NULL")
    )
    stage: Mapped[str] = mapped_column(sa.String(64))
    title: Mapped[str] = mapped_column(sa.String(300))
    description: Mapped[str | None] = mapped_column(sa.Text)
    authority_type: Mapped[AuthorityType]
    authority_id: Mapped[uuid.UUID | None] = mapped_column(sa.ForeignKey("authorities.id"))
    channel: Mapped[Channel]
    estimated_days: Mapped[int] = mapped_column(default=1)
    floor: Mapped[int | None]
    required_documents: Mapped[list[str]] = mapped_column(JSONB, default=list)
    optional: Mapped[bool] = mapped_column(default=False)
    is_form4_gate: Mapped[bool] = mapped_column(default=False)
    order: Mapped[int]
    status: Mapped[RequirementStatus] = mapped_column(default=RequirementStatus.not_started)
    status_changed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    due_date: Mapped[date | None]
    completed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    origin: Mapped[RequirementOrigin] = mapped_column(default=RequirementOrigin.template)
    # What it came from: the permit condition's id, or the city list entry ("<code>:<key>").
    origin_ref: Mapped[str | None] = mapped_column(sa.String(100))


class Dependency(Base):
    __tablename__ = "dependencies"

    requirement_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("requirements.id", ondelete="CASCADE"), primary_key=True
    )
    depends_on_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("requirements.id", ondelete="CASCADE"), primary_key=True
    )


# --- Documents and mail ---------------------------------------------------------------


class Document(IdMixin, TimestampMixin, Base):
    """A file in the project folder: uploaded by a person or received as an email attachment."""

    __tablename__ = "documents"

    project_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    # None means not filed yet.
    requirement_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("requirements.id", ondelete="SET NULL"), index=True
    )
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("messages.id", ondelete="SET NULL"), index=True
    )
    storage_key: Mapped[str] = mapped_column(sa.String(300), unique=True)
    file_name: Mapped[str] = mapped_column(sa.String(255))
    content_type: Mapped[str] = mapped_column(sa.String(150))
    size_bytes: Mapped[int] = mapped_column(sa.BigInteger)
    source: Mapped[DocumentSource]
    status: Mapped[DocumentStatus] = mapped_column(default=DocumentStatus.pending)
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(sa.ForeignKey("users.id"))
    # Uploaded through a professional's request link: the request, and who they are.
    request_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("document_requests.id", ondelete="SET NULL")
    )
    uploader_name: Mapped[str | None] = mapped_column(sa.String(200))
    # Arba's check of the document once it is filed under a step (see modules/checks).
    check_status: Mapped[CheckVerdict | None]
    check_result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    checked_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))


class Thread(IdMixin, TimestampMixin, Base):
    """A conversation with one counterparty, usually about one requirement."""

    __tablename__ = "threads"

    project_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    requirement_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("requirements.id", ondelete="SET NULL"), index=True
    )
    subject: Mapped[str] = mapped_column(sa.String(500))
    # Lowercased, without Re:/Fwd: prefixes; used to group replies that lost their headers.
    normalized_subject: Mapped[str] = mapped_column(sa.String(500), index=True)
    counterparty_email: Mapped[str] = mapped_column(sa.String(320))
    counterparty_name: Mapped[str | None] = mapped_column(sa.String(200))
    last_message_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))


class Message(IdMixin, TimestampMixin, Base):
    __tablename__ = "messages"
    __table_args__ = (sa.UniqueConstraint("project_id", "rfc_message_id", name="project_rfc_id"),)

    project_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    thread_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("threads.id", ondelete="CASCADE"), index=True
    )
    direction: Mapped[MessageDirection]
    from_email: Mapped[str] = mapped_column(sa.String(320))
    from_name: Mapped[str | None] = mapped_column(sa.String(200))
    to: Mapped[list[str]] = mapped_column(JSONB, default=list)
    cc: Mapped[list[str]] = mapped_column(JSONB, default=list)
    subject: Mapped[str] = mapped_column(sa.String(500))
    # Plain text only. HTML bodies are converted on arrival and never rendered.
    text_body: Mapped[str] = mapped_column(sa.Text, default="")
    # The RFC 5322 Message-ID, lowercased without angle brackets.
    rfc_message_id: Mapped[str] = mapped_column(sa.String(500))
    in_reply_to: Mapped[str | None] = mapped_column(sa.String(500))
    references: Mapped[list[str]] = mapped_column(JSONB, default=list)
    sent_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    read_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    inbound_email_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("inbound_emails.id", ondelete="SET NULL")
    )


class InboundEmail(IdMixin, Base):
    """Every webhook delivery, stored before processing so nothing is lost if processing fails."""

    __tablename__ = "inbound_emails"
    __table_args__ = (
        sa.UniqueConstraint("provider", "provider_message_id", name="provider_message"),
    )

    provider: Mapped[str] = mapped_column(sa.String(32))
    provider_message_id: Mapped[str] = mapped_column(sa.String(200))
    raw_key: Mapped[str] = mapped_column(sa.String(300))
    status: Mapped[InboundStatus] = mapped_column(default=InboundStatus.received)
    error: Mapped[str | None] = mapped_column(sa.Text)
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("projects.id", ondelete="SET NULL"), index=True
    )
    received_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    processed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))


class Suggestion(IdMixin, TimestampMixin, Base):
    """Arba's proposal for filing a thread or document, waiting for a person to approve it."""

    __tablename__ = "suggestions"

    project_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    # Exactly one of thread_id / document_id is set.
    thread_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("threads.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("messages.id", ondelete="SET NULL")
    )
    requirement_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("requirements.id", ondelete="SET NULL")
    )
    kind: Mapped[MessageKind]
    suggested_status: Mapped[RequirementStatus | None]
    summary: Mapped[str] = mapped_column(sa.Text)
    reason: Mapped[str] = mapped_column(sa.Text)
    confidence: Mapped[float]
    source: Mapped[str] = mapped_column(sa.String(16))
    model: Mapped[str | None] = mapped_column(sa.String(64))
    input_tokens: Mapped[int | None]
    output_tokens: Mapped[int | None]
    status: Mapped[SuggestionStatus] = mapped_column(default=SuggestionStatus.pending, index=True)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(sa.ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    applied_requirement_id: Mapped[uuid.UUID | None]
    # What the authority said is missing (requests for information and rejections).
    missing_documents: Mapped[list[str]] = mapped_column(JSONB, default=list)
    # Set when the suggestion came from importing an existing project's mailbox.
    scan_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("mailbox_scans.id", ondelete="SET NULL"), index=True
    )


class MailboxScan(IdMixin, TimestampMixin, Base):
    """One search of a person's mailbox for an existing project's mail.

    The access token is never stored: the scan runs while the person's one-time grant is
    valid, and scanning again means granting access again.
    """

    __tablename__ = "mailbox_scans"

    project_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("users.id"))
    provider: Mapped[MailboxProvider]
    account_email: Mapped[str] = mapped_column(sa.String(320))
    status: Mapped[ScanStatus] = mapped_column(default=ScanStatus.running)
    # The mailbox search Arba ran, shown to the person.
    query: Mapped[str] = mapped_column(sa.Text)
    messages_found: Mapped[int] = mapped_column(default=0)
    messages_imported: Mapped[int] = mapped_column(default=0)
    files_imported: Mapped[int] = mapped_column(default=0)
    error: Mapped[str | None] = mapped_column(sa.Text)
    finished_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))


# --- Notifications --------------------------------------------------------------------


class PhoneVerification(IdMixin, Base):
    __tablename__ = "phone_verifications"

    user_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    phone: Mapped[str] = mapped_column(sa.String(20))
    code_hash: Mapped[str] = mapped_column(sa.String(64))
    attempts: Mapped[int] = mapped_column(default=0)
    expires_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    verified_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )


class Notification(IdMixin, Base):
    """Something a person should know or do. Always shown in the app; pushed by channel."""

    __tablename__ = "notifications"
    __table_args__ = (sa.UniqueConstraint("user_id", "dedupe_key", name="user_dedupe"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[NotificationKind]
    urgency: Mapped[Urgency]
    title: Mapped[str] = mapped_column(sa.String(200))
    body: Mapped[str] = mapped_column(sa.Text)
    # Path inside the web app, e.g. /projects/<id>?tab=inbox&thread=<id>.
    action_path: Mapped[str | None] = mapped_column(sa.String(300))
    suggestion_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("suggestions.id", ondelete="SET NULL")
    )
    # WhatsApp template name and parameters, so a delivery can be retried as-is.
    whatsapp: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    dedupe_key: Mapped[str | None] = mapped_column(sa.String(200))
    read_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), index=True
    )


class Delivery(IdMixin, Base):
    __tablename__ = "deliveries"
    __table_args__ = (
        sa.UniqueConstraint("notification_id", "channel", name="notification_channel"),
    )

    notification_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("notifications.id", ondelete="CASCADE"), index=True
    )
    channel: Mapped[DeliveryChannel]
    status: Mapped[DeliveryStatus] = mapped_column(default=DeliveryStatus.queued, index=True)
    due_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), index=True)
    attempts: Mapped[int] = mapped_column(default=0)
    provider_message_id: Mapped[str | None] = mapped_column(sa.String(200), index=True)
    error: Mapped[str | None] = mapped_column(sa.Text)
    sent_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()
    )


class SimulatedWhatsApp(IdMixin, Base):
    """Messages of the dev WhatsApp simulator, in both directions."""

    __tablename__ = "simulated_whatsapp"

    phone: Mapped[str] = mapped_column(sa.String(20), index=True)
    direction: Mapped[str] = mapped_column(sa.String(8))
    text: Mapped[str] = mapped_column(sa.Text)
    # [{"id": "...", "title": "..."}] for messages with reply buttons.
    buttons: Mapped[list[dict[str, str]]] = mapped_column(JSONB, default=list)
    provider_message_id: Mapped[str] = mapped_column(sa.String(64))
    status: Mapped[str] = mapped_column(sa.String(16), default="delivered")
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )


# --- Audit ----------------------------------------------------------------------------


class AuditLog(IdMixin, Base):
    __tablename__ = "audit_log"

    organization_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("organizations.id"))
    project_id: Mapped[uuid.UUID | None] = mapped_column(sa.ForeignKey("projects.id"), index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(sa.ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(sa.String(64))
    entity: Mapped[str] = mapped_column(sa.String(64))
    entity_id: Mapped[uuid.UUID | None]
    before: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )


# --- Checklist completeness -----------------------------------------------------------


class PermitCondition(IdMixin, TimestampMixin, Base):
    """A condition written in the building permit, and how it entered the checklist."""

    __tablename__ = "permit_conditions"

    project_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    # As numbered in the permit, when it is.
    number: Mapped[str | None] = mapped_column(sa.String(16))
    text: Mapped[str] = mapped_column(sa.Text)
    # A short step title, when the condition becomes a step of its own.
    title: Mapped[str] = mapped_column(sa.String(300))
    timing: Mapped[ConditionTiming]
    stage: Mapped[str] = mapped_column(sa.String(64))
    authority_type: Mapped[AuthorityType]
    documents: Mapped[list[str]] = mapped_column(JSONB, default=list)
    # Arba's proposal: an existing step this belongs to (null: a new step).
    match_requirement_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("requirements.id", ondelete="SET NULL")
    )
    status: Mapped[ConditionStatus] = mapped_column(default=ConditionStatus.proposed)
    # The step it ended up in.
    requirement_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("requirements.id", ondelete="SET NULL")
    )
    source: Mapped[str] = mapped_column(sa.String(16))


class ChecklistFeedback(IdMixin, TimestampMixin, Base):
    """An authority asked for something: evidence for improving the base checklist."""

    __tablename__ = "checklist_feedback"

    project_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    requirement_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("requirements.id", ondelete="SET NULL")
    )
    template_requirement_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("template_requirements.id", ondelete="SET NULL"), index=True
    )
    authority_type: Mapped[AuthorityType]
    municipality_code: Mapped[int | None]
    kind: Mapped[MessageKind]
    summary: Mapped[str] = mapped_column(sa.Text)
    # Documents the authority wanted that the step didn't list.
    new_documents: Mapped[list[str]] = mapped_column(JSONB, default=list)
    suggestion_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("suggestions.id", ondelete="SET NULL")
    )


# --- Writing to authorities -----------------------------------------------------------


class OutboundDraft(IdMixin, TimestampMixin, Base):
    """A request or reminder Arba wrote to an approving body. Sent only after a person
    approves it."""

    __tablename__ = "outbound_drafts"

    project_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    requirement_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("requirements.id", ondelete="CASCADE"), index=True
    )
    thread_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("threads.id", ondelete="SET NULL")
    )
    authority_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("authorities.id", ondelete="SET NULL")
    )
    kind: Mapped[DraftKind]
    # email: Arba sends it. portal / in_person: the person submits the text themselves.
    channel: Mapped[Channel]
    to_email: Mapped[str | None] = mapped_column(sa.String(320))
    to_name: Mapped[str | None] = mapped_column(sa.String(200))
    portal_url: Mapped[str | None] = mapped_column(sa.String(500))
    phone: Mapped[str | None] = mapped_column(sa.String(40))
    subject: Mapped[str] = mapped_column(sa.String(300))
    body: Mapped[str] = mapped_column(sa.Text)
    attachment_ids: Mapped[list[str]] = mapped_column(JSONB, default=list)
    # Documents the authority will likely want that the project doesn't have yet.
    missing_documents: Mapped[list[str]] = mapped_column(JSONB, default=list)
    status: Mapped[DraftStatus] = mapped_column(default=DraftStatus.draft, index=True)
    source: Mapped[str] = mapped_column(sa.String(16))
    model: Mapped[str | None] = mapped_column(sa.String(64))
    decided_by: Mapped[uuid.UUID | None] = mapped_column(sa.ForeignKey("users.id"))
    sent_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("messages.id", ondelete="SET NULL")
    )
    # Where the address came from, shown next to it.
    recipient_source: Mapped[str | None] = mapped_column(sa.String(32))


class StoredFile(Base):
    """File bodies, when the storage backend is the database (serverless hosting)."""

    __tablename__ = "stored_files"

    key: Mapped[str] = mapped_column(sa.String(300), primary_key=True)
    content_type: Mapped[str] = mapped_column(sa.String(150))
    size: Mapped[int]
    data: Mapped[bytes] = mapped_column(sa.LargeBinary)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )


class AppMeta(Base):
    """Small facts about the installation, e.g. which reference data was last loaded."""

    __tablename__ = "app_meta"

    key: Mapped[str] = mapped_column(sa.String(64), primary_key=True)
    value: Mapped[str] = mapped_column(sa.Text)


# --- The project team -----------------------------------------------------------------


class ProjectContact(IdMixin, TimestampMixin, Base):
    """A professional working on the project: surveyor, engineer, lab, contractor…"""

    __tablename__ = "project_contacts"

    project_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[AuthorityType]
    name: Mapped[str] = mapped_column(sa.String(200))
    email: Mapped[str | None] = mapped_column(sa.String(320))
    phone: Mapped[str | None] = mapped_column(sa.String(20))


class DocumentRequest(IdMixin, TimestampMixin, Base):
    """Documents asked of a professional, who uploads them through a personal link without an
    account. The token is kept so the person can copy or resend the link; it grants only
    uploading to this request and seeing what it asks for."""

    __tablename__ = "document_requests"

    project_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    requirement_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("requirements.id", ondelete="CASCADE"), index=True
    )
    contact_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("project_contacts.id", ondelete="CASCADE")
    )
    token: Mapped[str] = mapped_column(sa.String(64), unique=True)
    documents: Mapped[list[str]] = mapped_column(JSONB, default=list)
    note: Mapped[str | None] = mapped_column(sa.Text)
    status: Mapped[RequestStatus] = mapped_column(default=RequestStatus.open, index=True)
    expires_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    requested_by: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("users.id"))
    sent_count: Mapped[int] = mapped_column(default=0)
    last_sent_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    fulfilled_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
