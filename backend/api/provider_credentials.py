from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.auth import CurrentUserDependency
from backend.api.ownership import get_owned_provider_credential
from backend.credential_security import (
    CredentialCipher,
    CredentialPayload,
    get_credential_cipher,
    key_hint,
)
from backend.db.models import ProviderCredential, Variant
from backend.db.session import get_db_session
from backend.provider_catalog import PROVIDER_CATALOG
from backend.schemas import (
    ProviderCatalogEntry,
    ProviderCredentialCreate,
    ProviderCredentialRead,
    ProviderCredentialTestRead,
    ProviderCredentialTestRequest,
    ProviderCredentialUpdate,
    ProviderModelCatalogRead,
    ProviderModelEntry,
)
from backend.services.model_catalog import (
    ProviderModelCatalogProtocol,
    get_provider_model_catalog,
)
from backend.services.provider_credentials import (
    ProviderCredentialTesterProtocol,
    get_provider_credential_tester,
)

router = APIRouter(prefix="/api/v1", tags=["provider credentials"])
SessionDependency = Annotated[AsyncSession, Depends(get_db_session)]
CipherDependency = Annotated[CredentialCipher, Depends(get_credential_cipher)]
TesterDependency = Annotated[
    ProviderCredentialTesterProtocol,
    Depends(get_provider_credential_tester),
]
ModelCatalogDependency = Annotated[
    ProviderModelCatalogProtocol,
    Depends(get_provider_model_catalog),
]
Offset = Annotated[int, Query(ge=0)]
Limit = Annotated[int, Query(ge=1, le=100)]


def _payload_from_create(payload: ProviderCredentialCreate) -> CredentialPayload:
    return {
        "api_key": payload.api_key.get_secret_value(),
        "api_base": payload.api_base,
    }


def _read_credential(
    credential: ProviderCredential,
    cipher: CredentialCipher,
) -> ProviderCredentialRead:
    payload = cipher.decrypt(credential.encrypted_payload)
    return ProviderCredentialRead(
        id=credential.id,
        provider=credential.provider,
        name=credential.name,
        key_hint=credential.key_hint,
        api_base=payload["api_base"],
        status=credential.status,
        last_checked_at=credential.last_checked_at,
        last_used_at=credential.last_used_at,
        created_at=credential.created_at,
        updated_at=credential.updated_at,
    )


async def _commit(session: AsyncSession, detail: str) -> None:
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=detail,
        ) from exc


@router.get("/providers/catalog", response_model=list[ProviderCatalogEntry])
async def list_provider_catalog(
    _current_user: CurrentUserDependency,
) -> list[ProviderCatalogEntry]:
    return [
        ProviderCatalogEntry(
            slug=provider.slug,
            label=provider.label,
            model_prefix=provider.model_prefix,
            api_key_placeholder=provider.api_key_placeholder,
            supports_custom_base_url=provider.supports_custom_base_url,
        )
        for provider in PROVIDER_CATALOG
    ]


@router.post(
    "/provider-credentials",
    response_model=ProviderCredentialRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_provider_credential(
    payload: ProviderCredentialCreate,
    session: SessionDependency,
    cipher: CipherDependency,
    current_user: CurrentUserDependency,
) -> ProviderCredentialRead:
    if payload.provider == "custom" and payload.api_base is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Custom providers require api_base",
        )
    secret_payload = _payload_from_create(payload)
    credential = ProviderCredential(
        user_id=current_user.id,
        provider=payload.provider,
        name=payload.name,
        encrypted_payload=cipher.encrypt(secret_payload),
        key_hint=key_hint(secret_payload["api_key"]),
        status="untested",
    )
    session.add(credential)
    await _commit(
        session,
        "A credential with this provider and name already exists",
    )
    await session.refresh(credential)
    return _read_credential(credential, cipher)


@router.get("/provider-credentials", response_model=list[ProviderCredentialRead])
async def list_provider_credentials(
    session: SessionDependency,
    cipher: CipherDependency,
    current_user: CurrentUserDependency,
    offset: Offset = 0,
    limit: Limit = 100,
) -> list[ProviderCredentialRead]:
    credentials = list(
        (
            await session.scalars(
                select(ProviderCredential)
                .where(ProviderCredential.user_id == current_user.id)
                .order_by(
                    ProviderCredential.provider,
                    ProviderCredential.name,
                    ProviderCredential.id,
                )
                .offset(offset)
                .limit(limit)
            )
        ).all()
    )
    return [_read_credential(credential, cipher) for credential in credentials]


@router.get(
    "/provider-credentials/{credential_id}/models",
    response_model=ProviderModelCatalogRead,
)
async def list_provider_models(
    credential_id: uuid.UUID,
    session: SessionDependency,
    cipher: CipherDependency,
    catalog: ModelCatalogDependency,
    current_user: CurrentUserDependency,
    refresh: bool = Query(default=False),
) -> ProviderModelCatalogRead:
    credential = await get_owned_provider_credential(
        session, current_user.id, credential_id
    )
    result = await catalog.discover(
        credential.provider,
        cipher.decrypt(credential.encrypted_payload),
        cache_key=f"{credential.id}:{credential.updated_at.isoformat()}",
        force_refresh=refresh,
    )
    return ProviderModelCatalogRead(
        credential_id=credential.id,
        provider=credential.provider,
        models=[
            ProviderModelEntry(id=model, label=model)
            for model in result.models
        ],
        source=result.source,
        cached=result.cached,
        refreshed_at=result.refreshed_at,
        warning=result.warning,
    )


@router.patch(
    "/provider-credentials/{credential_id}",
    response_model=ProviderCredentialRead,
)
async def update_provider_credential(
    credential_id: uuid.UUID,
    payload: ProviderCredentialUpdate,
    session: SessionDependency,
    cipher: CipherDependency,
    current_user: CurrentUserDependency,
) -> ProviderCredentialRead:
    credential = await get_owned_provider_credential(
        session, current_user.id, credential_id
    )
    current_payload = cipher.decrypt(credential.encrypted_payload)
    changes = payload.model_dump(exclude_unset=True)
    if "name" in changes:
        credential.name = changes["name"]
    if "api_key" in changes:
        api_key = changes["api_key"].get_secret_value()
        current_payload["api_key"] = api_key
        credential.key_hint = key_hint(api_key)
    if "api_base" in changes:
        current_payload["api_base"] = changes["api_base"]
    if {"api_key", "api_base"}.intersection(changes):
        credential.encrypted_payload = cipher.encrypt(current_payload)
        credential.status = "untested"
        credential.last_checked_at = None
    await _commit(
        session,
        "A credential with this provider and name already exists",
    )
    await session.refresh(credential)
    return _read_credential(credential, cipher)


@router.delete(
    "/provider-credentials/{credential_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_provider_credential(
    credential_id: uuid.UUID,
    session: SessionDependency,
    current_user: CurrentUserDependency,
) -> Response:
    credential = await get_owned_provider_credential(
        session, current_user.id, credential_id
    )
    attached_variant_id = (
        await session.scalars(
            select(Variant.id)
            .where(Variant.credential_id == credential.id)
            .limit(1)
        )
    ).one_or_none()
    if attached_variant_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Credential is attached to one or more model variants",
        )
    await session.delete(credential)
    await _commit(
        session,
        "Credential is attached to one or more model variants",
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/provider-credentials/{credential_id}/test",
    response_model=ProviderCredentialTestRead,
)
async def test_provider_credential(
    credential_id: uuid.UUID,
    payload: ProviderCredentialTestRequest,
    session: SessionDependency,
    cipher: CipherDependency,
    tester: TesterDependency,
    current_user: CurrentUserDependency,
) -> ProviderCredentialTestRead:
    credential = await get_owned_provider_credential(
        session, current_user.id, credential_id
    )
    checked_at = datetime.now(UTC)
    try:
        await tester.test(
            payload.model,
            cipher.decrypt(credential.encrypted_payload),
        )
    except Exception as exc:
        credential.status = "invalid"
        credential.last_checked_at = checked_at
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provider credential test failed",
        ) from exc

    credential.status = "connected"
    credential.last_checked_at = checked_at
    await session.commit()
    return ProviderCredentialTestRead(
        status=credential.status,
        checked_at=checked_at,
    )
