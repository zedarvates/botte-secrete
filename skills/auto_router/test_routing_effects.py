"""Offline regressions for routing choices, cache reuse and execution evidence."""

from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from skills.auto_router import effort
from skills.tiered_router import Tier, TieredRouter

router_mod = import_module("skills.auto_router.router")
cli_mod = import_module("skills.auto_router.cli")
fusion_mod = import_module("skills.auto_router.fusion")


class RoutingEffectsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        previous_cwd = Path.cwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, previous_cwd)
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.dict(os.environ, {"BOTTE_NN_AUTO_LABELS": "0"}))
        cache_mod = import_module("skills.response_cache")
        self.cache = cache_mod.ResponseCache(str(self.root / "cache"), learn=False)
        self.stack.enter_context(patch.object(cache_mod, "_cache", self.cache))
        self.stack.enter_context(patch("urllib.request.urlopen", side_effect=AssertionError("network forbidden")))
        self.events = self.stack.enter_context(patch("skills.events.log_event"))
        self.stack.enter_context(patch("skills.control_loop.control_loop.record"))
        self.stack.enter_context(patch.object(router_mod.AutoRouter, "_log_observation", return_value=None))
        self.backend = SimpleNamespace(label="fixture", host="127.0.0.1", port=1234,
                                       base_url="http://127.0.0.1:1234")
        self.discovery = self.stack.enter_context(patch.object(
            router_mod.registry, "best_chat_backend", return_value=self.backend))
        self.stack.enter_context(patch.object(router_mod.registry, "preferred_model", return_value="fixture-model"))
        self.local = self.stack.enter_context(patch.object(
            router_mod.LocalLLMClient, "chat",
            return_value=SimpleNamespace(text="local fixture", total_tokens=7)))
        self.cloud = self.stack.enter_context(patch.object(
            router_mod, "_cloud_chat", return_value=("cloud fixture", 17)))

    def cloud_router(self):
        decision = router_mod.AutoDecision(
            mode="cloud", tier=Tier.CHEAP, effort=effort.estimate("x"),
            model="shared-model", base_url="https://one.invalid/v1", via="native")
        router = router_mod.AutoRouter()
        self.stack.enter_context(patch.object(router, "decide", return_value=decision))
        return router, decision

    def test_explicit_free_tier_is_preserved_by_both_routers(self):
        prompt = "Design a distributed system and prove correctness"
        with patch.object(router_mod.providers, "cheapest_cloud_at_least") as providers:
            providers.return_value = SimpleNamespace(tier=Tier.PREMIUM, model="expensive",
                label="fixture", base_url="https://unused.invalid/v1", via="native", api_key="fixture")
            router = router_mod.AutoRouter()
            decision = router.decide(prompt, force_tier=Tier.FREE)
            self.assertEqual((decision.mode, decision.tier), ("local", Tier.FREE))
            trace = router.explain(prompt, force_tier=Tier.FREE)
            self.assertEqual(trace["effort"]["tier"], "FREE")
            self.assertEqual(trace["belt"]["reason"], "forced tier")
            self.discovery.return_value = None
            self.assertEqual(router.decide(prompt, force_tier=Tier.FREE).mode, "none")
            providers.assert_not_called()
        self.assertEqual(TieredRouter().route("security_audit", prompt, force_tier=Tier.FREE)["tier"], Tier.FREE)

    def test_cache_preserves_prompt_whitespace(self):
        router, _ = self.cloud_router()
        prompts = ["if ready:\n    act()", "if ready:\nact()", "if ready: act()"]
        for prompt in prompts:
            self.assertNotIn("cached", router.run(prompt))
        self.assertEqual(self.cloud.call_count, 3)
        self.assertTrue(router.run(prompts[0])["cached"])
        self.assertEqual(self.cloud.call_count, 3)

    def test_cache_separates_projects_and_resolves_equivalent_paths(self):
        router, _ = self.cloud_router()
        router.run("same", project_root=str(self.root / "alpha"))
        self.assertNotIn("cached", router.run("same", project_root=str(self.root / "beta")))
        self.assertTrue(router.run("same", project_root=str(self.root / "alpha" / ".." / "alpha"))["cached"])
        self.assertEqual(self.cloud.call_count, 2)

    def test_cache_separates_selected_endpoints_and_routes(self):
        router, decision = self.cloud_router()
        router.run("same")
        decision.base_url = "https://two.invalid/v1"
        self.assertNotIn("cached", router.run("same"))
        decision.via = "openrouter"
        self.assertNotIn("cached", router.run("same"))
        decision.base_url += "/"
        self.assertTrue(router.run("same")["cached"])
        self.assertEqual(self.cloud.call_count, 3)

    def test_legacy_cache_entry_is_not_reused_without_scope(self):
        router, decision = self.cloud_router()
        context = json.dumps({"system": "", "task_type": "", "max_tokens": 1024,
                              "mode": "cloud"}, ensure_ascii=False, sort_keys=True)
        self.cache.set("same", "legacy", model=decision.model, context=context)
        self.assertEqual(router.run("same")["text"], "cloud fixture")
        self.cloud.assert_called_once()

    def test_unresolved_cache_scope_does_not_block_inference(self):
        router, _ = self.cloud_router()
        with patch.object(router_mod.Path, "resolve", side_effect=RuntimeError("fixture symlink loop")):
            self.assertEqual(router.run("same")["text"], "cloud fixture")
        self.cloud.assert_called_once()
        self.assertEqual(self.cache.report()["entries"], 0)

    def test_local_failure_does_not_claim_a_cloud_escalation(self):
        self.local.side_effect = router_mod.LocalLLMError("fixture failure")
        result = router_mod.AutoRouter().run("same", force_tier=Tier.LOCAL)
        self.assertIn("error", result)
        self.cloud.assert_not_called()
        self.assertNotIn("escalate", [call.args[0] for call in self.events.call_args_list])
        from skills.trajectory.outcome import load_outcomes
        rows = load_outcomes(str(self.root))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "FAIL")
        self.assertFalse(rows[0]["verified"])

    def test_run_cli_returns_failure_with_its_json_error(self):
        for result in ({"error": "no backend"}, {"error": "local failure"}, {"text": "answer"}):
            with self.subTest(result=result), patch.object(cli_mod, "auto_run", return_value=result):
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    code = cli_mod.main(["run", "fixture"])
                self.assertEqual(json.loads(output.getvalue()), result)
                self.assertEqual(code, 1 if "error" in result else 0)

    def test_draft_fusion_transmits_question_and_local_draft_to_refiner(self):
        with patch.object(fusion_mod, "_run_local", return_value="fixture draft"), patch.object(
                fusion_mod, "_run_cloud", return_value=("refined", "fixture cloud")) as refine:
            result = fusion_mod.draft_refine("fixture question")
        self.assertIn("fixture question", refine.call_args.args[1])
        self.assertIn("fixture draft", refine.call_args.args[1])
        self.assertEqual(result["answer"], "refined")

    def test_vote_sends_prompt_to_each_available_cloud_candidate(self):
        candidates = [SimpleNamespace(tier=Tier.CHEAP, model=f"model-{n}", label=f"model-{n}",
            base_url=f"https://cloud-{n}.invalid/v1", via="native", api_key="fixture") for n in range(2)]
        with patch.object(fusion_mod.providers, "available_cloud", return_value=candidates), patch.object(
                fusion_mod, "_cloud_chat", return_value=("same answer", 11)) as cloud:
            result = fusion_mod.vote("fixture question", include_local=False)
        self.assertEqual([call.args[0].base_url for call in cloud.call_args_list], [c.base_url for c in candidates])
        self.assertEqual(result["total"], 2)
        self.assertEqual(result["agreement"], 1.0)  # Agreement is not an independent correctness check.


if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(RoutingEffectsTests))
    failed = len({getattr(test, "test_case", test).id() for test, _ in result.failures + result.errors})
    print(f"RESULT: {result.testsRun - failed} passed, {failed} failed")
    raise SystemExit(0 if result.wasSuccessful() else 1)
