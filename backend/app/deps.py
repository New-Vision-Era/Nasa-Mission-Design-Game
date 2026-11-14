"""FastAPI dependencies: the service container and the logged-in player."""

from typing import Annotated, Optional

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.app.container import Container
from backend.app.errors import ApiError
from backend.app.schemas import User

_bearer = HTTPBearer(auto_error=False)


def get_container(request: Request) -> Container:
    return request.app.state.container


ContainerDep = Annotated[Container, Depends(get_container)]
_Credentials = Annotated[Optional[HTTPAuthorizationCredentials], Depends(_bearer)]


def optional_user(container: ContainerDep, credentials: _Credentials) -> Optional[User]:
    """The player if a valid token was sent; None for a guest."""
    if credentials is None:
        return None
    user = container.auth.user_for_token(credentials.credentials)
    if user is None:
        raise ApiError(401, "invalid_token", "Your session is invalid or has expired. Log in again.")
    return user


OptionalUser = Annotated[Optional[User], Depends(optional_user)]


def current_user(user: OptionalUser) -> User:
    if user is None:
        raise ApiError(401, "not_authenticated", "Log in to use this feature.")
    return user


CurrentUser = Annotated[User, Depends(current_user)]


def bearer_token(credentials: _Credentials) -> str:
    if credentials is None:
        raise ApiError(401, "not_authenticated", "Log in to use this feature.")
    return credentials.credentials


BearerToken = Annotated[str, Depends(bearer_token)]
