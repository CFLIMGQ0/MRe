"""Smoke and contract tests for the ten Bernoulli-view/KAN ideas."""

from __future__ import annotations

import json
import unittest

import torch

from models.layers.kan import KANLinear
from models.layers.pc_cmka import IDEA_MODES, PCCMKADDKACEncoder
from utils.pc_cmka import load_pc_cmka_config


CONFIG = "configs/pc_cmka_ddkac_word.json"


def chain(size: int) -> torch.Tensor:
    adjacency = torch.zeros(size, size)
    indices = torch.arange(size - 1)
    adjacency[indices, indices + 1] = 1.0
    adjacency[indices + 1, indices] = 1.0
    return adjacency


class KANInspectionContractTests(unittest.TestCase):
    def test_edge_contributions_sum_to_unchanged_forward(self) -> None:
        torch.manual_seed(3)
        layer = KANLinear(4, 3, grid_size=5)
        inputs = torch.randn(2, 4).clamp(-0.9, 0.9)
        torch.testing.assert_close(
            layer.edge_outputs(inputs).sum(dim=-1),
            layer(inputs),
            atol=1e-6,
            rtol=1e-6,
        )

    def test_zero_spline_adapter_is_original_function(self) -> None:
        layer = KANLinear(4, 3, grid_size=5)
        inputs = torch.randn(2, 4).clamp(-0.9, 0.9)
        delta = torch.zeros(
            2, 3, 4, layer.grid_size + layer.spline_order
        )
        torch.testing.assert_close(
            layer.forward_with_spline_delta(inputs, delta), layer(inputs)
        )


class BernoulliKANIdeaTests(unittest.TestCase):
    dims = (5, 6, 7, 8, 9, 10)

    @classmethod
    def setUpClass(cls) -> None:
        raw = json.loads(open(CONFIG, encoding="utf-8").read())
        cls.names = [
            item["name"] for item in raw["bernoulli_kan_experiments"]
        ]

    def _encoder(self, name: str) -> PCCMKADDKACEncoder:
        config = load_pc_cmka_config(CONFIG, name)
        return PCCMKADDKACEncoder(
            self.dims,
            [chain(size) for size in self.dims],
            config,
            output_dim=8,
        )

    def _inputs(self) -> list[torch.Tensor]:
        return [torch.randn(size) for size in self.dims]

    def test_all_ten_modes_resolve_exactly_once(self) -> None:
        self.assertEqual(len(self.names), 10)
        self.assertEqual(len(set(self.names)), 10)
        resolved_modes = {
            load_pc_cmka_config(CONFIG, name)["bernoulli_kan"]["mode"]
            for name in self.names
        }
        self.assertEqual(resolved_modes, set(IDEA_MODES))

    def test_all_ten_modes_forward_backward_and_remain_finite(self) -> None:
        for name in self.names:
            with self.subTest(experiment=name):
                torch.manual_seed(11)
                model = self._encoder(name)
                model.train()
                output = model(self._inputs())
                self.assertEqual(tuple(output.shape), (1, 6, 8))
                loss = output.square().mean() + model.auxiliary_loss
                self.assertTrue(bool(torch.isfinite(loss)))
                loss.backward()
                gradient = sum(
                    float(parameter.grad.detach().abs().sum())
                    for parameter in model.parameters()
                    if parameter.grad is not None
                )
                self.assertGreater(gradient, 0.0)
                self.assertIn("bernoulli_kan", model.loss_components)

    def test_controller_modes_receive_real_downstream_gradient(self) -> None:
        for name in (
            "BK_I04_kan2bern_controller",
            "BK_I10_sensitivity_correlated_views",
        ):
            with self.subTest(experiment=name):
                torch.manual_seed(17)
                model = self._encoder(name)
                model.train()
                output = model(self._inputs())
                output.square().mean().backward()
                self.assertTrue(
                    all(
                        pathway.augmenter.feedback_updates > 0
                        for pathway in model.pathways
                    )
                )
                self.assertTrue(
                    all(
                        float(pathway.augmenter.feedback_sensitivity.sum()) > 0.0
                        for pathway in model.pathways
                    )
                )

    def test_eval_uses_deterministic_base_graph(self) -> None:
        for name in self.names:
            with self.subTest(experiment=name):
                torch.manual_seed(23)
                model = self._encoder(name)
                model.eval()
                inputs = self._inputs()
                with torch.no_grad():
                    first = model(inputs)
                    second = model(inputs)
                torch.testing.assert_close(first, second)


if __name__ == "__main__":
    unittest.main()
