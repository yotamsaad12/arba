import uuid
from datetime import date, datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import (
    AuthorityType,
    Channel,
    ClientType,
    DependencyKind,
    OrgRole,
    ProjectRole,
    ProjectStatus,
    Repeat,
    RequirementStatus,
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
    """A specific approving body, with contact details per municipality (milestone 3+)."""

    __tablename__ = "authorities"

    type: Mapped[AuthorityType]
    name: Mapped[str] = mapped_column(sa.String(200))
    municipality: Mapped[str | None] = mapped_column(sa.String(200))
    email: Mapped[str | None] = mapped_column(sa.String(320))
    phone: Mapped[str | None] = mapped_column(sa.String(32))
    notes: Mapped[str | None] = mapped_column(sa.Text)


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


class Dependency(Base):
    __tablename__ = "dependencies"

    requirement_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("requirements.id", ondelete="CASCADE"), primary_key=True
    )
    depends_on_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("requirements.id", ondelete="CASCADE"), primary_key=True
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
