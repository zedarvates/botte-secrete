"""nn_audit — audit micro-NNs: grounded in real data, or synthetic copies of rules?

    from skills.nn_audit import audit_models
    audit_models("skills/botte_nn")   # per-model data_source + verdict, 0 tokens
"""

from skills.nn_audit.audit import audit_models

__all__ = ["audit_models"]
