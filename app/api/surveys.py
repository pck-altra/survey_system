"""Survey CRUD endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status
from bson import ObjectId

from ..models import SurveyRepo
from ..models.surveys import SurveyStateError
from .deps import CurrentUser, DbDep
from .schemas import SurveyCreate, SurveyOut, SurveyUpdate, SurveyListOut

router = APIRouter()


def _survey_out(doc: dict) -> SurveyOut:
    return SurveyOut(
        id=str(doc["_id"]),
        title=doc["title"],
        description=doc.get("description", ""),
        allow_anonymous=doc.get("allow_anonymous", False),
        owner_id=str(doc["owner_id"]),
        status=doc["status"],
        token=doc.get("token"),
        deadline=doc.get("deadline"),
        created_at=doc["created_at"],
        published_at=doc.get("published_at"),
    )


@router.post("/", response_model=SurveyOut, status_code=status.HTTP_201_CREATED)
def create_survey(body: SurveyCreate, current_user: CurrentUser, db: DbDep) -> SurveyOut:
    """Create a new draft survey owned by the current user."""
    repo = SurveyRepo(db=db)
    try:
        sid = repo.create(
            title=body.title,
            owner_id=ObjectId(current_user["_id"]),
            description=body.description,
            allow_anonymous=body.allow_anonymous,
        )
    except SurveyStateError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    return _survey_out(repo.get(sid))


@router.get("/", response_model=SurveyListOut)
def list_my_surveys(
    current_user: CurrentUser,
    limit: int = Query(50, ge=1, le=200),
    db: DbDep = None,
) -> SurveyListOut:
    """List all surveys owned by the current user."""
    repo = SurveyRepo(db=db)
    docs = repo.list_by_owner(ObjectId(current_user["_id"]), limit=limit)
    return SurveyListOut(
        items=[_survey_out(d) for d in docs],
        total=len(docs),
    )


@router.get("/{survey_id}", response_model=SurveyOut)
def get_survey(survey_id: str, current_user: CurrentUser, db: DbDep = None) -> SurveyOut:
    """Get a single survey by ID (owner only)."""
    try:
        oid = ObjectId(survey_id)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid survey_id")

    repo = SurveyRepo(db=db)
    doc = repo.get(oid)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="survey not found")
    if doc["owner_id"] != current_user["_id"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not the owner")

    return _survey_out(doc)


@router.patch("/{survey_id}", response_model=SurveyOut)
def update_survey(
    survey_id: str,
    body: SurveyUpdate,
    current_user: CurrentUser,
    db: DbDep = None,
) -> SurveyOut:
    """Update a draft survey's metadata (owner only)."""
    try:
        oid = ObjectId(survey_id)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid survey_id")

    repo = SurveyRepo(db=db)
    doc = repo.get(oid)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="survey not found")
    if doc["owner_id"] != current_user["_id"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not the owner")
    if doc["status"] != "draft":
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="only draft surveys can be updated")

    updates = {}
    if body.title is not None:
        updates["title"] = body.title.strip()
    if body.description is not None:
        updates["description"] = body.description
    if body.allow_anonymous is not None:
        updates["allow_anonymous"] = body.allow_anonymous
    if body.deadline is not None:
        updates["deadline"] = body.deadline

    if updates:
        repo._coll.update_one({"_id": oid}, {"$set": updates})

    return _survey_out(repo.get(oid))


@router.post("/{survey_id}/publish", response_model=SurveyOut)
def publish_survey(survey_id: str, current_user: CurrentUser, db: DbDep = None) -> SurveyOut:
    """Publish a draft survey (draft → published). Returns the token."""
    try:
        oid = ObjectId(survey_id)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid survey_id")

    repo = SurveyRepo(db=db)
    doc = repo.get(oid)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="survey not found")
    if doc["owner_id"] != current_user["_id"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not the owner")

    try:
        repo.publish(oid)
    except SurveyStateError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    return _survey_out(repo.get(oid))


@router.post("/{survey_id}/close", response_model=SurveyOut)
def close_survey(survey_id: str, current_user: CurrentUser, db: DbDep = None) -> SurveyOut:
    """Close a published survey (published → closed)."""
    try:
        oid = ObjectId(survey_id)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid survey_id")

    repo = SurveyRepo(db=db)
    doc = repo.get(oid)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="survey not found")
    if doc["owner_id"] != current_user["_id"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not the owner")

    try:
        repo.close(oid)
    except SurveyStateError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    return _survey_out(repo.get(oid))


@router.delete("/{survey_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_survey(
    survey_id: str,
    current_user: CurrentUser,
    db: DbDep = None,
):
    """Delete a draft survey and all its questions/submissions (owner only)."""
    try:
        oid = ObjectId(survey_id)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid survey_id")

    repo = SurveyRepo(db=db)
    try:
        deleted = repo.delete(oid, ObjectId(current_user["_id"]))
    except PermissionError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not the owner")
    except SurveyStateError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="survey not found")


@router.get("/token/{token}", response_model=SurveyOut)
def get_survey_by_token(token: str, db: DbDep = None) -> SurveyOut:
    """Public endpoint: look up a published survey by its access token."""
    repo = SurveyRepo(db=db)
    doc = repo.find_by_token(token)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="survey not found")
    return _survey_out(doc)
