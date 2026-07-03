from __future__ import annotations

from fastapi import APIRouter, Depends, File, Request, UploadFile
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppException, ErrorCode
from app.core.responses import success_response
from app.db.session import get_db
from app.models.enums import EvidenceAvailability
from app.repositories.evidence_packages import EvidencePackageRepository
from app.repositories.references import ReferenceRepository
from app.repositories.source_metadata import SourceMetadataRepository
from app.services.doi_metadata_lookup import MetadataLookupService
from app.services.evidence_package_builder import EvidencePackageBuilder
from app.services.reference_extraction import get_reference
from app.services.verification_orchestrator import VerificationOrchestrator

router = APIRouter(prefix="/references", tags=["references"])


@router.get("/{reference_id}")
async def reference_details(request: Request, reference_id: str, db: Session = Depends(get_db)):
    data = get_reference(reference_id, db)
    return success_response(request=request, data=data, message="Reference details returned")


@router.post("/{reference_id}/verify-doi")
async def verify_reference_doi(request: Request, reference_id: str, db: Session = Depends(get_db)):
    data = MetadataLookupService().verify_reference_doi(
        reference_id,
        db,
        request_id=getattr(request.state, "request_id", None),
    )
    return success_response(request=request, data=data, message="Reference DOI metadata lookup completed")


@router.get("/{reference_id}/metadata")
async def reference_metadata(request: Request, reference_id: str, db: Session = Depends(get_db)):
    data = MetadataLookupService().get_reference_metadata(reference_id, db)
    return success_response(request=request, data=data, message="Reference metadata returned")


@router.post("/{reference_id}/upload-source-pdf")
async def upload_source_pdf(
    request: Request,
    reference_id: str,
    file: UploadFile = File(..., description="PDF of the cited source paper (e.g. from institutional access)."),
    db: Session = Depends(get_db),
):
    """Upload a PDF for a paywalled reference so its full text can be used for verification.

    After uploading, run POST /documents/{document_id}/prepare-evidence to rebuild
    the evidence packages — the reference will then show FULL_TEXT_AVAILABLE.
    """
    settings = get_settings()
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise AppException(
            status_code=400,
            code=ErrorCode.FILE_REQUIRED,
            field="file",
            detail="Only PDF files are accepted.",
            message="Invalid file type",
        )
    pdf_bytes = await file.read()
    if len(pdf_bytes) > settings.fulltext_max_bytes:
        raise AppException(
            status_code=413,
            code=ErrorCode.FILE_REQUIRED,
            field="file",
            detail=f"File exceeds the maximum allowed size of {settings.fulltext_max_bytes // (1024 * 1024)} MB.",
            message="File too large",
        )
    upload_result = MetadataLookupService().inject_fulltext_from_uploaded_pdf(
        reference_id=reference_id,
        pdf_bytes=pdf_bytes,
        filename=file.filename,
        db=db,
    )

    reference = ReferenceRepository(db).get(reference_id)
    affected_claim_ids = [
        link.claim_id
        for link in (reference.claim_links or [])
        if link.claim_id
    ] if reference else []

    verification_result: dict = {}
    if affected_claim_ids and reference:
        request_id = getattr(request.state, "request_id", None)

        # Patch only the EvidencePackages for this reference with the new
        # full text — avoids rebuilding the entire document's packages.
        metadata = SourceMetadataRepository(db).get_latest_for_reference(reference_id)
        raw = metadata.raw_metadata_json if metadata else {}
        new_full_text: str | None = raw.get("full_text") if isinstance(raw, dict) else None
        if new_full_text:
            for pkg in EvidencePackageRepository(db).list_for_reference(reference_id):
                pkg.source_evidence_text = new_full_text
                pkg.evidence_availability = EvidenceAvailability.FULL_TEXT_AVAILABLE.value
            db.commit()

        verification_result = VerificationOrchestrator().run_document_verification(
            reference.document_id,
            db,
            mode="FULL_VERIFICATION",
            use_cache=False,
            use_rag=True,
            use_genai_safety_review=True,
            generate_report=False,
            claim_ids=affected_claim_ids,
            request_id=request_id,
        )

    data = {**upload_result, "re_verification": verification_result}
    return success_response(request=request, data=data, message="Source PDF uploaded and affected claims re-verified")


@router.post("/{reference_id}/re-verify")
async def re_verify_reference_claims(request: Request, reference_id: str, db: Session = Depends(get_db)):
    """Re-verify only the claims that cite this reference.

    Call this after POST /{reference_id}/upload-source-pdf to re-run the RAG
    pipeline exclusively for the affected claims instead of the full document.
    """
    reference = ReferenceRepository(db).get(reference_id)
    if not reference:
        raise AppException(
            status_code=404,
            code=ErrorCode.REFERENCE_NOT_FOUND,
            field="reference_id",
            detail=f"Reference '{reference_id}' was not found.",
            message="Reference not found",
        )

    affected_claim_ids = [
        link.claim_id
        for link in (reference.claim_links or [])
        if link.claim_id
    ]
    if not affected_claim_ids:
        return success_response(
            request=request,
            data={"reference_id": reference_id, "affected_claims_count": 0},
            message="No claims cite this reference — nothing to re-verify.",
        )

    request_id = getattr(request.state, "request_id", None)

    # Rebuild evidence packages for the document so the new full text is picked
    # up by the RAG pipeline before verification runs.
    EvidencePackageBuilder().prepare_evidence_for_document(
        reference.document_id, db, request_id=request_id
    )

    data = VerificationOrchestrator().run_document_verification(
        reference.document_id,
        db,
        mode="FULL_VERIFICATION",
        use_cache=False,
        use_rag=True,
        use_genai_safety_review=True,
        generate_report=False,
        claim_ids=affected_claim_ids,
        request_id=request_id,
    )
    data["affected_claim_ids"] = affected_claim_ids
    return success_response(request=request, data=data, message="Re-verification of affected claims completed")
