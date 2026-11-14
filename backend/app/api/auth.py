from fastapi import APIRouter

from backend.app.deps import BearerToken, ContainerDep, CurrentUser
from backend.app.schemas import AuthResponse, Credentials, User

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=AuthResponse, status_code=201)
def register(body: Credentials, container: ContainerDep) -> AuthResponse:
    """Create an account and log in. Returns a bearer token."""
    return container.auth.register(body.username, body.password)


@router.post("/login", response_model=AuthResponse)
def login(body: Credentials, container: ContainerDep) -> AuthResponse:
    return container.auth.login(body.username, body.password)


@router.post("/logout", status_code=204)
def logout(token: BearerToken, container: ContainerDep) -> None:
    container.auth.logout(token)


@router.get("/me", response_model=User)
def me(user: CurrentUser) -> User:
    return user
