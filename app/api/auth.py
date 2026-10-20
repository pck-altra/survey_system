"""Authentication endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from ..models import UserRepo
from ..models.users import UsernameError, PasswordError
from .deps import create_access_token, CurrentUser, DbDep
from .schemas import Token, UserCreate, UserOut

router = APIRouter()


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(body: UserCreate, db: DbDep) -> UserOut:
    """Register a new user account."""
    repo = UserRepo(db=db)
    try:
        user_id = repo.create(body.username, body.password)
    except UsernameError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except PasswordError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except Exception as exc:
        # DuplicateKeyError → 409 Conflict
        if "duplicate key" in str(exc).lower():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"username {body.username!r} is already taken",
            )
        raise

    user = repo.find_by_id(user_id)
    return UserOut(
        id=str(user["_id"]),
        username=user["username"],
        created_at=user["created_at"],
    )


@router.post("/login", response_model=Token)
def login(username: str, password: str, db: DbDep) -> Token:
    """Authenticate and return a JWT access token."""
    repo = UserRepo(db=db)
    user = repo.verify_credentials(username, password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token(str(user["_id"]))
    return Token(access_token=access_token)


@router.get("/me", response_model=UserOut)
def me(current_user: CurrentUser) -> UserOut:
    """Return the currently authenticated user."""
    return UserOut(
        id=str(current_user["_id"]),
        username=current_user["username"],
        created_at=current_user["created_at"],
    )
