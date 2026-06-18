"""bootstrap — deploy Botte Secrète's token-saving stack into a project.

    from skills.bootstrap import setup
    setup("/path/to/project", create_agents_md=True)

Wires .mcp.json (botte-llm tools), audits agent directives, writes .botte/config
and a setup report. The capstone: this is how a project actually starts saving
tokens/cost with the toolkit.
"""

from skills.bootstrap.setup import setup, wire_mcp, write_config, ensure_agents_md

__all__ = ["setup", "wire_mcp", "write_config", "ensure_agents_md"]
