"""Read-only launch guard tests using packaged official metadata."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("native_launch", ROOT / "scripts/run_repository_baseline.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class RepositoryLaunchTests(unittest.TestCase):
    def plan(self, *args):
        return module.build_plan(module.parser().parse_args(args))

    def test_ld_full_keeps_native_generator(self):
        plan = self.plan("--model", "ld_cvae", "--cohort", "brca")
        self.assertIn("--generator", plan["argv"])
        self.assertIn("--g_condition", plan["argv"])
        self.assertEqual(plan["argv"][plan["argv"].index("--missing_rate") + 1], "0.0")
        self.assertNotIn("--lr", plan["argv"])
        self.assertNotIn("--max_epochs", plan["argv"])
        self.assertFalse(plan["ready"])

    def test_missing_modality_flag_is_explicit(self):
        full = self.plan("--model", "slotspe", "--cohort", "blca")
        missing = self.plan("--model", "slotspe", "--cohort", "blca", "--evaluation", "missing")
        self.assertNotIn("--omic_missing", full["argv"])
        self.assertIn("--omic_missing", missing["argv"])

    def test_dimaf_native_shape_loss_and_path(self):
        plan = self.plan("--model", "dimaf", "--cohort", "blca")
        self.assertIn("cox_distcor", plan["argv"])
        self.assertEqual(plan["argv"][plan["argv"].index("--w_dis") + 1], "7")
        self.assertTrue(plan["argv"][plan["argv"].index("--data_source") + 1].endswith("/"))
        self.assertGreater(plan["required_slides"], 0)
        self.assertEqual(plan["missing_slide_count"], plan["required_slides"])

    def test_no_invented_cohort(self):
        plan = self.plan("--model", "dimaf", "--cohort", "hnsc")
        self.assertFalse(plan["ready"])
        self.assertTrue(any("no packaged native cohort" in s for s in plan["blockers"]))

    def test_no_missing_slide_zero_fill(self):
        plan = self.plan("--model", "slotspe", "--cohort", "blca")
        self.assertGreater(plan["required_slides"], 0)
        self.assertTrue(any("NOT be replaced with zeros" in s for s in plan["blockers"]))

    def test_no_overwrite(self):
        with tempfile.TemporaryDirectory(prefix="native_launch_guard_") as tmp:
            plan = self.plan("--model", "slotspe", "--cohort", "blca", "--output", tmp)
        self.assertTrue(any("overwriting is forbidden" in s for s in plan["blockers"]))

    def test_wrong_model_prototype_stage_rejected(self):
        plan = self.plan("--model", "slotspe", "--stage", "prototypes")
        self.assertFalse(plan["ready"])
        self.assertTrue(any("belongs to DIMAF" in s for s in plan["blockers"]))

    def test_invalid_plan_cannot_execute(self):
        args = module.parser().parse_args(["--model", "dimaf", "--cohort", "hnsc", "--execute"])
        with self.assertRaisesRegex(RuntimeError, "preflight failed"):
            module.execute(module.build_plan(args), args)


if __name__ == "__main__":
    unittest.main()
