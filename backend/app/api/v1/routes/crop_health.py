"""Authenticated crop health report endpoints."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.api.dependencies import CurrentUser, DatabaseSession
from app.domain.models import CropHealthReport, Farm, FarmerCrop
from app.schemas.crop_health import CropHealthReportCreate, CropHealthReportResponse

router = APIRouter(prefix="/crop-health/reports")


@router.post("", response_model=CropHealthReportResponse, status_code=status.HTTP_201_CREATED)
def create_report(
    request: CropHealthReportCreate,
    user: CurrentUser,
    session: DatabaseSession,
) -> CropHealthReportResponse:
    crop = session.scalar(
        select(FarmerCrop)
        .join(Farm, Farm.id == FarmerCrop.farm_id)
        .where(
            FarmerCrop.id == request.crop_id,
            FarmerCrop.farm_id == request.farm_id,
            Farm.owner_id == user.id,
            FarmerCrop.farmer_id == user.id,
        )
    )
    if crop is None:
        raise HTTPException(status_code=404, detail="Farm or crop not found")

    report = CropHealthReport(
        owner_id=user.id,
        farm_id=request.farm_id,
        crop_id=request.crop_id,
        symptoms=[symptom.value for symptom in request.symptoms],
        duration_days=request.duration_days,
        notes=request.notes,
        farm=crop.farm,
        farmer_crop=crop,
    )
    session.add(report)
    session.commit()
    session.refresh(report)
    return CropHealthReportResponse.model_validate(report)


@router.get("", response_model=list[CropHealthReportResponse])
def list_reports(
    user: CurrentUser,
    session: DatabaseSession,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
) -> list[CropHealthReportResponse]:
    reports = session.scalars(
        select(CropHealthReport)
        .where(CropHealthReport.owner_id == user.id)
        .order_by(CropHealthReport.created_at.desc(), CropHealthReport.id.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    return [CropHealthReportResponse.model_validate(report) for report in reports]


@router.get("/{report_id}", response_model=CropHealthReportResponse)
def get_report(
    report_id: UUID,
    user: CurrentUser,
    session: DatabaseSession,
) -> CropHealthReportResponse:
    report = session.scalar(
        select(CropHealthReport).where(
            CropHealthReport.id == report_id,
            CropHealthReport.owner_id == user.id,
        )
    )
    if report is None:
        raise HTTPException(status_code=404, detail="Crop health report not found")
    return CropHealthReportResponse.model_validate(report)
