"""Direct Bernoulli graph-view and KAN coupling experiments.

The ten modes in this module share the same input/output contract: three sets
of six pathway tokens are received and six tokens are returned.  The module is
therefore an internal genomic refinement layer and does not alter MRePath's
public model interface.
"""

from __future__ import annotations

from typing import Any

import torch
import torch.nn as nn
import torch.nn.functional as F

from models.layers.kan import KANGeneAggregator, KANLinear


IDEA_MODES = (
    "bv_jetkan",
    "uvr_kan",
    "mask2spline_hyperkan",
    "kan2bern_controller",
    "bml_kan",
    "bernoulli_jensen_debiased",
    "overlap_calibrated_jacobian",
    "bernoulli_barycentric_grid",
    "stable_cross_pathway_gate",
    "sensitivity_correlated_views",
)


def _mean_square(first: torch.Tensor, second: torch.Tensor) -> torch.Tensor:
    return (first - second).square().mean()


class MaskConditionedKANAggregator(nn.Module):
    """Low-rank mask-conditioned adapter on pathway-mixer spline weights."""

    def __init__(
        self,
        embedding_dim: int,
        num_pathways: int,
        rank: int,
        dropout: float,
        grid_size: int,
    ) -> None:
        super().__init__()
        bottleneck = max(embedding_dim // 2, 32)
        hidden = num_pathways * 2
        self.feature_encoder = nn.Sequential(
            KANLinear(embedding_dim, bottleneck, grid_size=grid_size),
            nn.Dropout(dropout),
            KANLinear(bottleneck, embedding_dim, grid_size=grid_size),
        )
        self.mixer_in = KANLinear(num_pathways, hidden, grid_size=grid_size)
        self.dropout = nn.Dropout(dropout)
        self.mixer_out = KANLinear(hidden, num_pathways, grid_size=grid_size)
        self.norm = nn.LayerNorm(embedding_dim)
        self.hypernetwork = nn.Sequential(
            nn.Linear(5, 32), nn.GELU(), nn.Linear(32, rank), nn.Tanh()
        )
        basis = self.mixer_in.grid_size + self.mixer_in.spline_order
        self.adapter_left = nn.Parameter(torch.empty(hidden, rank))
        self.adapter_right = nn.Parameter(
            torch.empty(rank, num_pathways, basis)
        )
        nn.init.normal_(self.adapter_left, std=0.02)
        nn.init.normal_(self.adapter_right, std=0.02)
        self.last_delta_norm = torch.tensor(0.0)

    def forward(
        self, genomics: torch.Tensor, mask_summary: torch.Tensor
    ) -> torch.Tensor:
        batch, _, embedding = genomics.shape
        encoded = self.feature_encoder(genomics)
        mixer_inputs = encoded.transpose(1, 2).reshape(-1, genomics.shape[1])
        code = self.hypernetwork(mask_summary)
        delta = torch.einsum(
            "br,or,rik->boik",
            code,
            self.adapter_left,
            self.adapter_right,
        )
        delta = delta.repeat_interleave(embedding, dim=0)
        hidden = self.mixer_in.forward_with_spline_delta(mixer_inputs, delta)
        mixed = self.mixer_out(self.dropout(hidden)).reshape(
            batch, embedding, genomics.shape[1]
        )
        self.last_delta_norm = delta.square().mean()
        return self.norm(mixed.transpose(1, 2))


class BarycentricGridKANAggregator(nn.Module):
    """Set the first pathway KAN grid from the base/view 1-D barycenter."""

    def __init__(
        self,
        embedding_dim: int,
        num_pathways: int,
        dropout: float,
        grid_size: int,
        ema: float,
    ) -> None:
        super().__init__()
        self.aggregator = KANGeneAggregator(
            embedding_dim, num_pathways, dropout, grid_size=grid_size
        )
        initial = torch.linspace(-1.0, 1.0, grid_size + 1).expand(
            num_pathways, -1
        ).clone()
        self.register_buffer("barycentric_knots", initial)
        self.ema = float(ema)
        self.last_shift = torch.tensor(0.0)

    @torch.no_grad()
    def _update(
        self,
        base: torch.Tensor,
        positive: torch.Tensor,
        negative: torch.Tensor,
    ) -> None:
        layer = self.aggregator.pathway_mixer[0]
        quantiles = torch.linspace(
            0.0,
            1.0,
            layer.grid_size + 1,
            device=base.device,
            dtype=base.dtype,
        )
        distributions = []
        for tokens in (base, positive, negative):
            encoded = self.aggregator.feature_encoder(tokens)
            values = encoded.transpose(1, 2).reshape(-1, tokens.shape[1])
            distributions.append(
                torch.quantile(values.float(), quantiles.float(), dim=0).t()
                .to(dtype=base.dtype)
            )
        barycenter = torch.stack(distributions).mean(dim=0)
        previous = self.barycentric_knots.clone()
        self.barycentric_knots.mul_(self.ema).add_(
            barycenter, alpha=1.0 - self.ema
        )
        layer.set_grid_from_inner_knots(self.barycentric_knots)
        self.last_shift = (self.barycentric_knots - previous).abs().mean()

    def forward(
        self,
        base: torch.Tensor,
        positive: torch.Tensor,
        negative: torch.Tensor,
    ) -> torch.Tensor:
        if self.training:
            self._update(base, positive, negative)
        return self.aggregator(base)


class StableCrossPathwayKAN(nn.Module):
    """Gate each direct pathway-to-pathway spline by view stability."""

    def __init__(
        self,
        embedding_dim: int,
        num_pathways: int,
        dropout: float,
        grid_size: int,
        ema: float,
        temperature: float,
    ) -> None:
        super().__init__()
        bottleneck = max(embedding_dim // 2, 32)
        self.feature_encoder = nn.Sequential(
            KANLinear(embedding_dim, bottleneck, grid_size=grid_size),
            nn.Dropout(dropout),
            KANLinear(bottleneck, embedding_dim, grid_size=grid_size),
        )
        self.direct_mixer = KANLinear(
            num_pathways, num_pathways, grid_size=grid_size
        )
        self.post_mixer = KANLinear(
            num_pathways, num_pathways, grid_size=grid_size
        )
        self.norm = nn.LayerNorm(embedding_dim)
        self.register_buffer(
            "running_variance", torch.zeros(num_pathways, num_pathways)
        )
        self.ema = float(ema)
        self.temperature = float(temperature)
        self.last_gate = torch.ones(num_pathways, num_pathways)

    def _contributions(self, tokens: torch.Tensor) -> torch.Tensor:
        encoded = self.feature_encoder(tokens).transpose(1, 2)
        return self.direct_mixer.edge_outputs(encoded)

    def forward(
        self,
        base: torch.Tensor,
        positive: torch.Tensor,
        negative: torch.Tensor,
    ) -> torch.Tensor:
        base_edges = self._contributions(base)
        positive_edges = self._contributions(positive)
        negative_edges = self._contributions(negative)
        variance = 0.25 * (positive_edges - negative_edges).square()
        variance = variance.mean(dim=(0, 1))
        if self.training:
            with torch.no_grad():
                self.running_variance.mul_(self.ema).add_(
                    variance.detach(), alpha=1.0 - self.ema
                )
        gate = torch.exp(
            -self.running_variance / max(self.temperature, 1e-6)
        )
        gate = gate / gate.mean().clamp_min(1e-6)
        self.last_gate = gate.detach()
        direct = (base_edges * gate).sum(dim=-1)
        mixed = self.post_mixer(direct)
        return self.norm(mixed.transpose(1, 2))


class BernoulliKANInnovation(nn.Module):
    """Dispatcher implementing the ten Bernoulli-view/KAN research modes."""

    def __init__(
        self,
        embedding_dim: int,
        num_pathways: int,
        config: dict[str, Any],
    ) -> None:
        super().__init__()
        settings = dict(config.get("bernoulli_kan", {}))
        self.mode = str(settings.get("mode", "off"))
        if self.mode != "off" and self.mode not in IDEA_MODES:
            raise ValueError(f"unknown Bernoulli-KAN mode: {self.mode}")
        self.settings = settings
        self.num_pathways = int(num_pathways)
        self.embedding_dim = int(embedding_dim)
        dropout = float(settings.get("dropout", 0.25))
        grid_size = int(settings.get("grid_size", 5))
        self.shared = KANGeneAggregator(
            embedding_dim, num_pathways, dropout, grid_size=grid_size
        )
        self.coarse = None
        self.fine = None
        self.mask_conditioned = None
        self.residual_kan = None
        self.barycentric = None
        self.stable_gate = None
        if self.mode == "uvr_kan":
            self.coarse = KANGeneAggregator(
                embedding_dim,
                num_pathways,
                dropout,
                grid_size=int(settings.get("coarse_grid", 3)),
            )
            self.fine = KANGeneAggregator(
                embedding_dim,
                num_pathways,
                dropout,
                grid_size=int(settings.get("fine_grid", 7)),
            )
        elif self.mode == "mask2spline_hyperkan":
            self.mask_conditioned = MaskConditionedKANAggregator(
                embedding_dim,
                num_pathways,
                int(settings.get("adapter_rank", 4)),
                dropout,
                grid_size,
            )
        elif self.mode == "bml_kan":
            self.residual_kan = KANGeneAggregator(
                embedding_dim, num_pathways, dropout, grid_size=grid_size
            )
            self.lattice_scale = nn.Parameter(torch.tensor(0.1))
        elif self.mode == "bernoulli_barycentric_grid":
            self.barycentric = BarycentricGridKANAggregator(
                embedding_dim,
                num_pathways,
                dropout,
                grid_size,
                float(settings.get("ema", 0.95)),
            )
        elif self.mode == "stable_cross_pathway_gate":
            self.stable_gate = StableCrossPathwayKAN(
                embedding_dim,
                num_pathways,
                dropout,
                grid_size,
                float(settings.get("ema", 0.95)),
                float(settings.get("gate_temperature", 0.1)),
            )
        generator = torch.Generator().manual_seed(27011)
        projection = torch.empty(1, num_pathways, embedding_dim)
        projection.bernoulli_(0.5, generator=generator).mul_(2.0).sub_(1.0)
        projection = projection / projection.numel() ** 0.5
        self.register_buffer("jacobian_projection", projection)
        self.auxiliary_loss = torch.tensor(0.0)
        self.loss_components: dict[str, torch.Tensor] = {}
        self.diagnostics: dict[str, torch.Tensor] = {}

    def _projected_jacobian(self, tokens: torch.Tensor) -> torch.Tensor:
        output = self.shared(tokens)
        projection = self.jacobian_projection.expand_as(output)
        return torch.autograd.grad(
            (output * projection).sum(),
            tokens,
            create_graph=self.training,
            retain_graph=True,
        )[0]

    def _jensen_output(
        self,
        base: torch.Tensor,
        positive: torch.Tensor,
        negative: torch.Tensor,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        positive_output = self.shared(positive)
        negative_output = self.shared(negative)
        midpoint = 0.5 * (positive + negative)
        direction = 0.5 * (positive - negative)
        magnitude = direction.square().mean(dim=(1, 2), keepdim=True).sqrt()
        unit = direction / magnitude.clamp_min(1e-6)
        epsilon = float(self.settings.get("jensen_epsilon", 0.05))
        center_output = self.shared(midpoint)
        upper = self.shared(midpoint + epsilon * unit)
        lower = self.shared(midpoint - epsilon * unit)
        second = (upper - 2.0 * center_output + lower) / (epsilon ** 2)
        second = second * magnitude.square()
        corrected = 0.5 * (positive_output + negative_output) - 0.5 * second
        anchor = _mean_square(corrected, self.shared(base))
        return corrected, anchor

    def forward(
        self,
        base: torch.Tensor,
        positive: torch.Tensor,
        negative: torch.Tensor,
        metadata: dict[str, torch.Tensor],
    ) -> torch.Tensor:
        zero = base.new_zeros(())
        components = {
            "view": zero,
            "jacobian": zero,
            "anchor": zero,
            "adapter": zero,
            "lattice": zero,
        }
        if self.mode == "off":
            self.auxiliary_loss = zero
            self.loss_components = components
            self.diagnostics = {}
            return base

        if self.mode in {"bv_jetkan", "overlap_calibrated_jacobian"}:
            output = self.shared(base)
            if self.training:
                positive_output = self.shared(positive)
                negative_output = self.shared(negative)
                components["view"] = _mean_square(
                    positive_output, negative_output
                )
                positive_jacobian = self._projected_jacobian(positive)
                negative_jacobian = self._projected_jacobian(negative)
                difference = (
                    positive_jacobian - negative_jacobian
                ).square().mean(dim=2)
                if self.mode == "overlap_calibrated_jacobian":
                    overlap = metadata["overlap"].to(difference)
                    components["jacobian"] = (difference * overlap).mean()
                else:
                    components["jacobian"] = difference.mean()
        elif self.mode == "uvr_kan":
            uncertainty = (positive - negative).square().mean(dim=2)
            normalized = uncertainty / uncertainty.detach().mean(
                dim=1, keepdim=True
            ).clamp_min(1e-6)
            alpha = torch.exp(-float(self.settings.get("tau", 1.0)) * normalized)
            coarse = self.coarse(base)
            fine = self.fine(base)
            output = (1.0 - alpha.unsqueeze(2)) * coarse + alpha.unsqueeze(2) * fine
            components["view"] = _mean_square(
                self.shared(positive), self.shared(negative)
            )
            self.diagnostics["resolution_alpha"] = alpha.detach()
        elif self.mode == "mask2spline_hyperkan":
            output = self.mask_conditioned(base, metadata["mask_summary"])
            components["adapter"] = self.mask_conditioned.last_delta_norm
            components["anchor"] = _mean_square(output, self.shared(base))
        elif self.mode in {
            "kan2bern_controller",
            "sensitivity_correlated_views",
        }:
            base_output = self.shared(base)
            positive_output = self.shared(positive)
            negative_output = self.shared(negative)
            view_mean = 0.5 * (positive_output + negative_output)
            # Forward value equals the deterministic base prediction, while the
            # straight-through term sends the supervised survival gradient to
            # the sampled edge views for the next-step controller update.
            bridge = view_mean - view_mean.detach()
            output = base_output + float(
                self.settings.get("controller_gradient_scale", 1.0)
            ) * bridge
            components["view"] = _mean_square(positive_output, negative_output)
            components["anchor"] = _mean_square(view_mean, base_output)
        elif self.mode == "bml_kan":
            base_output = self.shared(base)
            positive_output = self.shared(positive)
            negative_output = self.shared(negative)
            intersection = self.shared(metadata["intersection"])
            union = self.shared(metadata["union"])
            valuation_residual = (
                positive_output + negative_output - intersection - union
            )
            learned_residual = self.residual_kan(valuation_residual)
            components["lattice"] = _mean_square(
                learned_residual, valuation_residual
            )
            output = base_output + torch.tanh(self.lattice_scale) * learned_residual
            self.diagnostics["valuation_residual"] = (
                valuation_residual.square().mean().detach()
            )
        elif self.mode == "bernoulli_jensen_debiased":
            output, components["anchor"] = self._jensen_output(
                base, positive, negative
            )
        elif self.mode == "bernoulli_barycentric_grid":
            output = self.barycentric(base, positive, negative)
            components["view"] = _mean_square(
                self.shared(positive), self.shared(negative)
            )
            self.diagnostics["grid_shift"] = self.barycentric.last_shift.detach()
            self.diagnostics["barycentric_knots"] = (
                self.barycentric.barycentric_knots.detach()
            )
        elif self.mode == "stable_cross_pathway_gate":
            output = self.stable_gate(base, positive, negative)
            self.diagnostics["stability_gate"] = self.stable_gate.last_gate
            components["view"] = _mean_square(
                self.shared(positive), self.shared(negative)
            )
        else:
            raise RuntimeError(f"unhandled mode: {self.mode}")

        weights = {
            "view": float(self.settings.get("lambda_view", 0.01)),
            "jacobian": float(self.settings.get("lambda_jacobian", 0.001)),
            "anchor": float(self.settings.get("lambda_anchor", 0.01)),
            "adapter": float(self.settings.get("lambda_adapter", 0.0001)),
            "lattice": float(self.settings.get("lambda_lattice", 0.01)),
        }
        self.loss_components = components
        self.auxiliary_loss = sum(weights[name] * value for name, value in components.items())
        self.diagnostics.update(
            {f"loss_{name}": value.detach() for name, value in components.items()}
        )
        return output


__all__ = ["BernoulliKANInnovation", "IDEA_MODES"]
