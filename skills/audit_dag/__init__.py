"""audit_dag — one canonical machine-first audit (a DAG of findings), two derived
views: ultra-compact for LLMs (every node addressable, nothing forgotten) and HTML
for humans. See skills/audit_dag/dag.py.
"""

from skills.audit_dag.dag import build_dag, AuditDAG, Node, Edge
from skills.audit_dag.render import to_compact, to_html

__all__ = ["build_dag", "AuditDAG", "Node", "Edge", "to_compact", "to_html"]
