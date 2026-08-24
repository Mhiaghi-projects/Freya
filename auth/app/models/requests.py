"""Esquemas pydantic de entrada de auth (docs/freya-api-contract.md §2, §15)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ServiceAuthRequest(BaseModel):
    """POST /authenticate/service (§15.2)."""

    service: str = Field(min_length=1)
    api_secret: str = Field(min_length=1)


class SignUpRequest(BaseModel):
    """POST /auth/sign-up (§2.1). Público."""

    email: str = Field(min_length=3)
    password: str = Field(min_length=8)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(default="", max_length=100)


class SignInRequest(BaseModel):
    """POST /auth/sign-in (§2.2)."""

    email: str = Field(min_length=3)
    password: str = Field(min_length=1)


class RefreshTokenRequest(BaseModel):
    """POST /auth/refresh-token (§2.3)."""

    refresh_token: str = Field(min_length=1)


class SignOutRequest(BaseModel):
    """POST /auth/sign-out (§2.4)."""

    refresh_token: str = Field(min_length=1)


class ChangePasswordRequest(BaseModel):
    """POST /auth/change-password. Autoservicio, requiere sesión propia."""

    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=8)


class ServiceAccountCreate(BaseModel):
    """POST /admin/service-accounts. Bootstrap o role: admin."""

    service: str = Field(min_length=1)
    api_secret: str = Field(min_length=16)
    permissions: list[str] = Field(default_factory=list)


class ServiceAccountPermissionsUpdate(BaseModel):
    """PATCH /admin/service-accounts/{service}. Bootstrap o role: admin.
    Reemplaza la lista completa de permisos, no la añade."""

    permissions: list[str] = Field(default_factory=list)


class AdminUserCreate(BaseModel):
    """POST /admin/users. Bootstrap o role: admin — a diferencia de
    /api/v1/auth/sign-up (público, siempre role="user"), aquí se puede pedir
    cualquier role de app.domain.users.ROLE_PERMISSIONS (validado ahí, no
    aquí, para no acoplar el modelo a la lista de roles conocida)."""

    email: str = Field(min_length=3)
    password: str = Field(min_length=8)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(default="", max_length=100)
    role: str = Field(default="user")
    # Sólo tiene efecto con role="user" -- validado contra
    # app.domain.users.SERVICE_GRANTS, no aquí.
    extra_permissions: list[str] = Field(default_factory=list)


class AdminPermissionsUpdate(BaseModel):
    """PATCH /admin/users/{user_id}/permissions. role: admin. Reemplaza la
    lista completa de extra_permissions, no la añade -- mismo patrón que
    ServiceAccountPermissionsUpdate."""

    extra_permissions: list[str] = Field(default_factory=list)


class UpdateThemeRequest(BaseModel):
    """PATCH /auth/me/theme. Autoservicio, requiere sesión propia. El valor
    se valida contra app.domain.users.THEMES, no aquí."""

    theme: str = Field(min_length=1)


class AdminPasswordReset(BaseModel):
    """POST /admin/users/{user_id}/reset-password. role: admin -- a
    diferencia de /auth/change-password (autoservicio), no exige la
    contraseña actual. Deja must_change_password=true: la persona la
    cambia ella misma en el primer login, el admin nunca llega a saberla."""

    new_password: str = Field(min_length=8)
