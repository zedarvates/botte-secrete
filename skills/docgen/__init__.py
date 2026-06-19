"""docgen — local-drafted docs (cloud-refined) + local session review.

    from skills.docgen import draft_doc, session_review
    draft_doc("how to deploy", kind="guide")     # local draft → cloud refine
    session_review("transcript.jsonl")            # 0 cloud tokens
"""

from skills.docgen.docgen import draft_doc, session_review

__all__ = ["draft_doc", "session_review"]
