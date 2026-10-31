"""Offline delivery checks for new projects and the installable plugin subset."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from skills.bootstrap import setup
from skills.preflight import hook, policy


ROOT = Path(__file__).resolve().parents[2]


class PortableGuidanceTests(unittest.TestCase):
    def test_fresh_bootstrap_delivers_policy_pointer_and_hook_guidance(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            with patch("skills.llm_backends.registry.refresh", return_value=[]):
                setup(project, create_agents_md=True)
            instructions = (project / "AGENTS.md").read_text(encoding="utf-8")
            self.assertIn(".botte/policy.md", instructions)
            self.assertIn("Parcimonia", instructions)
            self.assertIn(policy.PARCIMONIA_GUIDANCE, policy.load(project))
            settings = json.loads((project / ".claude/settings.json").read_text(encoding="utf-8"))
            command = settings["hooks"]["UserPromptSubmit"][0]["hooks"][0]
            self.assertIn(str(ROOT / "skills/preflight/hook.py"), command["command"])
            # Exercise the actual command from the new project, without relying
            # on the checkout cwd or an editable installation's import precedence.
            environment = os.environ.copy()
            environment.pop("PYTHONPATH", None)
            result = subprocess.run(
                shlex.split(command["command"]), cwd=project, env=environment,
                input=json.dumps({"prompt": "Run regression tests", "cwd": str(project)}),
                capture_output=True, text=True, encoding="utf-8", timeout=15,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.count("[botte preflight] Parcimonia:"), 1)
            self.assertIn("Parcimonia: software_testing", result.stdout)
            self.assertIn("no tool execution", result.stdout)
            self.assertIn("current tool schemas", result.stdout)
            self.assertLessEqual(len(result.stdout.encode("utf-8")), hook.MAX_CONTEXT_BYTES)
            self.assertNotIn("0 cloud tokens", result.stdout)
            noop = subprocess.run(
                shlex.split(command["command"]), cwd=project, env=environment,
                input=json.dumps({"prompt": "merci", "cwd": str(project)}),
                capture_output=True, text=True, encoding="utf-8", timeout=15,
            )
            self.assertEqual(noop.returncode, 0, noop.stderr)
            self.assertEqual(noop.stdout, "")

    def test_existing_custom_policy_and_hooks_survive_repeated_bootstrap(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project / ".botte").mkdir()
            custom_policy = "# Team policy\nKeep user-defined constraints.\n"
            policy.policy_path(project).write_text(custom_policy, encoding="utf-8")
            (project / "CLAUDE.md").write_text("# Team instructions\n", encoding="utf-8")
            (project / ".claude").mkdir()
            existing_hook = {"hooks": [{"type": "command", "command": "team-check"}]}
            (project / ".claude/settings.json").write_text(
                json.dumps({"hooks": {"UserPromptSubmit": [existing_hook]}}), encoding="utf-8",
            )
            with patch("skills.llm_backends.registry.refresh", return_value=[]):
                setup(project, create_agents_md=True)
                setup(project, create_agents_md=True)
            self.assertEqual(policy.load(project), custom_policy)
            instructions = (project / "CLAUDE.md").read_text(encoding="utf-8")
            self.assertTrue(instructions.startswith("# Team instructions\n"))
            self.assertEqual(instructions, "# Team instructions\n")
            agents = (project / "AGENTS.md").read_text(encoding="utf-8")
            self.assertIn("[CLAUDE.md](CLAUDE.md)", agents)
            self.assertEqual(agents.count(".botte/policy.md"), 1)
            hooks = json.loads((project / ".claude/settings.json").read_text(encoding="utf-8"))["hooks"]["UserPromptSubmit"]
            self.assertEqual(hooks[0], existing_hook)
            self.assertEqual(len(hooks), 2)

    def test_repository_policy_shares_the_generated_parcimonia_section(self):
        self.assertIn(policy.PARCIMONIA_GUIDANCE, policy.load(ROOT))

    def test_plugin_subset_delivers_guidance_through_its_declared_skill_path(self):
        # Resolve marketplace -> plugin -> skill after copying only the installable
        # subset: repo-level docs and personal skills cannot satisfy this contract.
        marketplace = json.loads((ROOT / ".agents/plugins/marketplace.json").read_text(encoding="utf-8"))
        entry = next(item for item in marketplace["plugins"] if item["name"] == "botte-secrete")
        source = ROOT / entry["source"]["path"]
        with tempfile.TemporaryDirectory() as directory:
            plugin = Path(directory) / "plugin"
            shutil.copytree(source, plugin)
            manifest = json.loads((plugin / ".codex-plugin/plugin.json").read_text(encoding="utf-8"))
            skill = plugin / manifest["skills"] / "botte-secrete/SKILL.md"
            self.assertTrue(skill.resolve().is_relative_to(plugin.resolve()))
            text = skill.read_text(encoding="utf-8")
            for requirement in ("assess_task", "plan_github_research", "homogeneous batch",
                                "absent, fails or abstains", "host choose", "overhead"):
                with self.subTest(requirement=requirement):
                    self.assertIn(requirement, text)


if __name__ == "__main__":
    unittest.main()
