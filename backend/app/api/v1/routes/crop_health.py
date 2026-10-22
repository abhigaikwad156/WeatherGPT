"""Authenticated crop health report endpoints."""

import json
import logging
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.api.dependencies import CurrentUser, DatabaseSession
from app.conversation.gemini import GeminiChatService, GeminiError
from app.core.config import get_settings
from app.rag.retrieval import RetrievalService
from app.services.conversations import _retrieval_service
from app.domain.models import CropHealthReport, Farm, FarmerCrop
from app.schemas.crop_health import (
    CropHealthAnalysisRequest,
    CropHealthAnalysisResponse,
    CropHealthReportCreate,
    CropHealthReportResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/crop-health")


@router.post("/reports", response_model=CropHealthReportResponse, status_code=status.HTTP_201_CREATED)
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


@router.post("/analyze", response_model=CropHealthAnalysisResponse)
def analyze_crop_health(
    request: CropHealthAnalysisRequest,
    user: CurrentUser,
    session: DatabaseSession,
) -> CropHealthAnalysisResponse:
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

    farm = crop.farm
    crop_name = crop.crop.name
    symptom_names = [symptom.value.replace("_", " ") for symptom in request.symptoms]
    question = (
        f"Possible disease explanations for {crop_name}"
        f"{f' ({crop.variety})' if crop.variety else ''}; "
        f"reported symptoms: {', '.join(symptom_names)}; "
        f"observed for {request.duration_days} days."
        + (f" Additional observations: {request.notes}" if request.notes else "")
    )
    farm_context = {
        "farm": farm.name,
        "location": farm.location_name,
        "soil_type": farm.soil_type,
        "irrigation_type": farm.irrigation_type,
        "soil_moisture_percent": farm.soil_moisture_percent,
        "crop": crop_name,
        "variety": crop.variety,
        "growth_stage": crop.growth_stage,
        "reported_symptoms": symptom_names,
        "duration_days": request.duration_days,
        "notes": request.notes,
    }

    language = user.preferred_language or "mr"
    try:
        retrieval = _retrieval_service(session)
        retrieved = retrieval.retrieve(question, limit=5)
        source_context = RetrievalService.context(retrieved)
        sources = [item["source"] for item in source_context]
        if not sources:
            return CropHealthAnalysisResponse(
                status="insufficient_information",
                analysis=None,
                follow_up=(
                    "No relevant verified agricultural sources were found. Please add "
                    "details such as which plant parts are affected, the appearance and "
                    "spread of symptoms, and recent changes in weather or care. Image "
                    "analysis is not available; describe what you observe."
                ),
                sources=[],
            )

        verified_context = (
            "Farm and crop details:\n"
            + json.dumps(farm_context, ensure_ascii=False, default=str)
            + "\n\nRetrieved agricultural source excerpts (the only evidence for disease "
            "explanations or management/prevention advice; cite each claim using its "
            "source_id):\n"
            + json.dumps(source_context, ensure_ascii=False)
        )
        prompt = (
            f"{question}\n\nAnalyze symptoms cautiously; this is not a confirmed diagnosis. "
            "Use only the supplied excerpts for disease explanations, management, or "
            "prevention claims. Separate possible explanations and their matching reported "
            "symptoms from safe management and prevention guidance. Cite source IDs for "
            "every source-supported claim. If a requested detail is not supported by an "
            "excerpt, say so and do not guess. Do not name pesticides or give chemical "
            "treatment instructions or dosages. If the evidence or symptoms are insufficient, "
            "say that clearly and ask targeted follow-up questions. Do not request or claim "
            "to analyze an image."
        )
        analysis = GeminiChatService(get_settings()).respond(prompt, language, verified_context)
    except (GeminiError, SQLAlchemyError, RuntimeError) as error:
        logger.exception("Crop health analysis service failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Crop health analysis is temporarily unavailable. Please try again.",
        ) from error

    return CropHealthAnalysisResponse(
        status="analysis",
        analysis=analysis,
        follow_up=None,
        sources=sources,
    )


@router.get("/reports", response_model=list[CropHealthReportResponse])
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


@router.get("/reports/{report_id}", response_model=CropHealthReportResponse)
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
