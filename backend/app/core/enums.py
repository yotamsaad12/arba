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
