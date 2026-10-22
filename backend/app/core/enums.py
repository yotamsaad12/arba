"""Domain enums. Member names equal their values, so the database stores readable strings."""

from enum import StrEnum


class ClientType(StrEnum):
    business = "business"
    private = "private"


class OrgRole(StrEnum):
    owner = "owner"
    admin = "admin"
    member = "member"


class ProjectRole(StrEnum):
    owner = "owner"
    manager = "manager"
    viewer = "viewer"


PROJECT_ROLE_RANK = {ProjectRole.viewer: 0, ProjectRole.manager: 1, ProjectRole.owner: 2}


class ProjectStatus(StrEnum):
    active = "active"
    completed = "completed"
    archived = "archived"


class RequirementStatus(StrEnum):
    not_started = "not_started"
    blocked = "blocked"
    ready = "ready"
    in_progress = "in_progress"
    waiting_for_authority = "waiting_for_authority"
    needs_fix = "needs_fix"
    done = "done"
    # Optional requirements (fire department, green building) that don't apply to this project.
    not_applicable = "not_applicable"


class Channel(StrEnum):
    email = "email"
    portal = "portal"
    in_person = "in_person"


class Repeat(StrEnum):
    none = "none"
    per_floor = "per_floor"


class DependencyKind(StrEnum):
    # Same floor when both sides repeat per floor; otherwise every instance of the parent.
    same = "same"
    # Floor N depends on floor N-1 of the parent.
    previous_floor = "previous_floor"


class AuthorityType(StrEnum):
    municipality = "municipality"
    water_corporation = "water_corporation"
    fire_department = "fire_department"
    home_front_command = "home_front_command"
    testing_lab = "testing_lab"
    surveyor = "surveyor"
    soil_consultant = "soil_consultant"
    structural_engineer = "structural_engineer"
    supervising_engineer = "supervising_engineer"
    electrical_inspector = "electrical_inspector"
    gas_installer = "gas_installer"
    plumber = "plumber"
    green_building_lab = "green_building_lab"
    contractor = "contractor"
    owner = "owner"


class DocumentSource(StrEnum):
    upload = "upload"
    email = "email"


class DocumentStatus(StrEnum):
    # Upload URL issued, file not confirmed yet.
    pending = "pending"
    ready = "ready"


class MessageDirection(StrEnum):
    inbound = "inbound"
    outbound = "outbound"


class InboundStatus(StrEnum):
    received = "received"
    processed = "processed"
    # No project owns any of the recipient addresses. Kept for review, never dropped.
    unroutable = "unroutable"
    duplicate = "duplicate"
    failed = "failed"


class MessageKind(StrEnum):
    approval = "approval"
    rejection = "rejection"
    request_for_info = "request_for_info"
    info = "info"
    other = "other"


class SuggestionStatus(StrEnum):
    pending = "pending"
    # Approved as suggested.
    accepted = "accepted"
    # Approved after the person picked a different requirement.
    changed = "changed"
    dismissed = "dismissed"
    # A newer message in the same thread replaced it.
    superseded = "superseded"


class NotificationKind(StrEnum):
    approval_needed = "approval_needed"
    authority_request = "authority_request"
    daily_digest = "daily_digest"
    whatsapp_connected = "whatsapp_connected"
    # A mailbox scan of an existing project finished.
    import_finished = "import_finished"
    # Sent from Settings to check that email and WhatsApp reach the person.
    test = "test"


class Urgency(StrEnum):
    # Pushed right away (or when the person's quiet hours end).
    urgent = "urgent"
    # Not pushed: shown in the app and included in the next morning summary.
    normal = "normal"


class DeliveryChannel(StrEnum):
    email = "email"
    whatsapp = "whatsapp"


class DeliveryStatus(StrEnum):
    queued = "queued"
    sent = "sent"
    delivered = "delivered"
    read = "read"
    failed = "failed"
    # The channel was off or not set up when it came due.
    skipped = "skipped"


class PermitStatus(StrEnum):
    # The project is open; the permit still has to be uploaded or checked.
    pending_verification = "pending_verification"
    # Arba read the permit and every automatic check passed.
    document_checked = "document_checked"
    # Someone confirmed the permit in the local committee's own system.
    committee_confirmed = "committee_confirmed"
    # A check failed (expired, wrong committee…); shown with the reasons.
    needs_attention = "needs_attention"


class ContactSource(StrEnum):
    # Read from the body's official website, with the page and date recorded.
    official_site = "official_site"
    # Entered by a user of a project.
    user = "user"
    # Learned from mail that arrived from this body and was filed under a project.
    learned = "learned"


class MailboxProvider(StrEnum):
    gmail = "gmail"
    # Dev and tests: sample mail built from the project, no Google account needed.
    simulator = "simulator"


class ScanStatus(StrEnum):
    running = "running"
    done = "done"
    failed = "failed"
