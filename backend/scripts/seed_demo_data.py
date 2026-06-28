from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db.init_db import init_db
from app.db.session import session_scope
from app.models import ClaimReferenceLink, VerificationResult
from app.models.enums import MappingStatus, SupportStatus
from app.repositories import ClaimRepository, DocumentRepository, ReferenceRepository


def seed_demo_data() -> dict[str, str]:
    init_db()
    with session_scope() as db:
        document = DocumentRepository(db).create(
            filename="demo_text.txt",
            title="BE-2 Demo Scientific Reference Document",
            upload_type="TEXT",
            status="UPLOADED",
            raw_text="Demo claim with a placeholder citation (Smith, 2024).",
            cleaned_text="Demo claim with a placeholder citation (Smith, 2024).",
            commit=False,
        )
        db.flush()
        reference = ReferenceRepository(db).create(
            document_id=document.id,
            reference_key="Smith2024",
            raw_reference="Smith, J. (2024). Demo reference title. Journal of Demo Studies.",
            extracted_title="Demo reference title",
            extracted_doi="10.0000/demo.2024",
            commit=False,
        )
        claim = ClaimRepository(db).create(
            document_id=document.id,
            claim_text="Demo systems can store claim-reference mappings before verification logic exists.",
            section_name="Introduction",
            commit=False,
        )
        db.flush()
        link = ClaimReferenceLink(
            document_id=document.id,
            claim_id=claim.id,
            reference_id=reference.id,
            mapping_status=MappingStatus.MAPPED.value,
            mapping_confidence=0.85,
            mapping_reason="Seed data only; no BE-4 extraction logic was executed.",
        )
        db.add(link)
        result = VerificationResult(
            document_id=document.id,
            claim_id=claim.id,
            reference_id=reference.id,
            support_status=SupportStatus.NEEDS_HUMAN_REVIEW.value,
            confidence=0.0,
            explanation="Seed result only. GenAI/RAG verification is deferred to BE-9/BE-10.",
            human_review_required=True,
        )
        db.add(result)
        db.flush()
        return {
            "document_id": document.id,
            "reference_id": reference.id,
            "claim_id": claim.id,
            "claim_reference_link_id": link.id,
            "verification_result_id": result.id,
        }


if __name__ == "__main__":
    created = seed_demo_data()
    print("Created BE-2 demo records:")
    for key, value in created.items():
        print(f"{key}: {value}")
