"""Authority staff login / logout / whoami (AUTH-01)."""

import uuid

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.session import get_session
from backend.models.authority import StaffUser
from backend.services.authority.auth import authenticate, end_session, require_staff, start_session

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=512)


class StaffRead(BaseModel):
    id: uuid.UUID
    email: str
    role: str


@router.post("/login", response_model=StaffRead)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> StaffRead:
    ip = request.client.host if request.client else "unknown"
    user = await authenticate(session, body.email, body.password, ip)
    start_session(response, user)
    return StaffRead(id=user.id, email=user.email, role=user.role)


@router.post("/logout", status_code=204)
async def logout(response: Response) -> Response:
    end_session(response)
    response.status_code = 204
    return response


@router.get("/me", response_model=StaffRead)
async def me(staff: StaffUser = Depends(require_staff)) -> StaffRead:
    return StaffRead(id=staff.id, email=staff.email, role=staff.role)
