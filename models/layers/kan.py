"""Small self-contained Kolmogorov-Arnold Network layers.

The implementation uses a learnable base branch and cubic B-spline edge
functions, following the standard KAN parameterization.  Keeping it local
avoids adding a second KAN package with its own CUDA/build requirements.
"""

from __future__ import annotations

import math

import torch
import torch.nn as nn
import torch.nn.functional as F


class KANLinear(nn.Module):
    """Linear-shaped KAN layer with learnable cubic B-spline edge functions."""

    def __init__(
        self,
        in_features: int,
        out_features: int,
        grid_size: int = 5,
        spline_order: int = 3,
        grid_range: tuple[float, float] = (-1.0, 1.0),
    ) -> None:
        super().__init__()
        if in_features <= 0 or out_features <= 0:
            raise ValueError("KAN feature dimensions must be positive")
        if grid_size <= 0 or spline_order <= 0:
            raise ValueError("KAN grid size and spline order must be positive")

        self.in_features = in_features
        self.out_features = out_features
        self.grid_size = grid_size
        self.spline_order = spline_order

        grid_step = (grid_range[1] - grid_range[0]) / grid_size
        grid = (
            torch.arange(
                -spline_order,
                grid_size + spline_order + 1,
                dtype=torch.float32,
            )
            * grid_step
            + grid_range[0]
        )
        self.register_buffer(
            "grid",
            grid.expand(in_features, -1).contiguous(),
            persistent=True,
        )

        self.base_weight = nn.Parameter(
            torch.empty(out_features, in_features)
        )
        self.spline_weight = nn.Parameter(
            torch.empty(
                out_features,
                in_features,
                grid_size + spline_order,
            )
        )
        self.reset_parameters()

    def reset_parameters(self) -> None:
        nn.init.kaiming_uniform_(self.base_weight, a=math.sqrt(5))
        nn.init.normal_(
            self.spline_weight,
            mean=0.0,
            std=0.1 / math.sqrt(self.in_features),
        )

    def b_splines(self, inputs: torch.Tensor) -> torch.Tensor:
        if inputs.ndim != 2 or inputs.shape[1] != self.in_features:
            raise ValueError(
                f"KAN inputs must be [batch, {self.in_features}]"
            )

        grid = self.grid
        values = inputs.unsqueeze(-1)
        bases = (
            (values >= grid[:, :-1])
            & (values < grid[:, 1:])
        ).to(inputs.dtype)

        for order in range(1, self.spline_order + 1):
            left_denominator = (
                grid[:, order:-1] - grid[:, : -(order + 1)]
            )
            right_denominator = (
                grid[:, order + 1 :] - grid[:, 1:-order]
            )
            left = (
                (values - grid[:, : -(order + 1)])
                / left_denominator
                * bases[:, :, :-1]
            )
            right = (
                (grid[:, order + 1 :] - values)
                / right_denominator
                * bases[:, :, 1:]
            )
            bases = left + right

        return bases.contiguous()

    def forward(self, inputs: torch.Tensor) -> torch.Tensor:
        original_shape = inputs.shape[:-1]
        flattened = inputs.reshape(-1, self.in_features)
        base_output = F.linear(F.silu(flattened), self.base_weight)
        spline_basis = self.b_splines(flattened).reshape(
            flattened.shape[0], -1
        )
        spline_output = F.linear(
            spline_basis,
            self.spline_weight.reshape(self.out_features, -1),
        )
        return (base_output + spline_output).reshape(
            *original_shape, self.out_features
        )

    def edge_outputs(self, inputs: torch.Tensor) -> torch.Tensor:
        """Return every output-input edge contribution without changing ``forward``.

        The last two dimensions are ``[out_features, in_features]``.  This is
        used only by the Bernoulli-view research modules that need to measure
        the stability of individual KAN spline edges.
        """

        original_shape = inputs.shape[:-1]
        flattened = inputs.reshape(-1, self.in_features)
        base_edges = (
            F.silu(flattened).unsqueeze(1)
            * self.base_weight.unsqueeze(0)
        )
        spline_basis = self.b_splines(flattened)
        spline_edges = torch.einsum(
            "nik,oik->noi", spline_basis, self.spline_weight
        )
        return (base_edges + spline_edges).reshape(
            *original_shape, self.out_features, self.in_features
        )

    def forward_with_spline_delta(
        self,
        inputs: torch.Tensor,
        spline_delta: torch.Tensor,
    ) -> torch.Tensor:
        """Evaluate a sample-conditioned additive spline-coefficient adapter.

        ``spline_delta`` must be broadcast-free and have shape
        ``[flat_batch, out_features, in_features, basis_count]``.  The normal
        ``forward`` path is intentionally untouched so existing checkpoints
        and validated experiments retain their original behavior.
        """

        original_shape = inputs.shape[:-1]
        flattened = inputs.reshape(-1, self.in_features)
        expected = (
            flattened.shape[0],
            self.out_features,
            self.in_features,
            self.grid_size + self.spline_order,
        )
        if tuple(spline_delta.shape) != expected:
            raise ValueError(
                f"spline_delta must be {expected}, got {tuple(spline_delta.shape)}"
            )
        base_output = F.linear(F.silu(flattened), self.base_weight)
        spline_basis = self.b_splines(flattened)
        weights = self.spline_weight.unsqueeze(0) + spline_delta
        spline_output = torch.einsum("nik,noik->no", spline_basis, weights)
        return (base_output + spline_output).reshape(
            *original_shape, self.out_features
        )

    @torch.no_grad()
    def set_grid_from_inner_knots(self, knots: torch.Tensor) -> None:
        """Replace the inner grid while retaining the existing coefficients."""

        expected = (self.in_features, self.grid_size + 1)
        if tuple(knots.shape) != expected:
            raise ValueError(f"knots must be {expected}, got {tuple(knots.shape)}")
        knots = knots.to(device=self.grid.device, dtype=self.grid.dtype)
        knots = torch.sort(knots, dim=1).values
        minimum_step = torch.finfo(knots.dtype).eps * 64
        for index in range(1, knots.shape[1]):
            knots[:, index] = torch.maximum(
                knots[:, index], knots[:, index - 1] + minimum_step
            )
        left_step = (knots[:, 1] - knots[:, 0]).clamp_min(minimum_step)
        right_step = (knots[:, -1] - knots[:, -2]).clamp_min(minimum_step)
        offsets = torch.arange(
            self.spline_order, 0, -1, device=knots.device, dtype=knots.dtype
        )
        left = knots[:, :1] - left_step.unsqueeze(1) * offsets.unsqueeze(0)
        right = knots[:, -1:] + right_step.unsqueeze(1) * offsets.flip(0).unsqueeze(0)
        full = torch.cat((left, knots, right), dim=1)
        if full.shape != self.grid.shape:
            raise RuntimeError(
                f"constructed grid {tuple(full.shape)} != {tuple(self.grid.shape)}"
            )
        self.grid.copy_(full)


class KANGeneAggregator(nn.Module):
    """KAN replacement for graph aggregation across six genomic signatures."""

    def __init__(
        self,
        embedding_dim: int = 256,
        num_pathways: int = 6,
        dropout: float = 0.25,
        grid_size: int = 5,
    ) -> None:
        super().__init__()
        bottleneck = max(embedding_dim // 2, 32)
        pathway_hidden = num_pathways * 2

        self.feature_encoder = nn.Sequential(
            KANLinear(embedding_dim, bottleneck, grid_size=grid_size),
            nn.Dropout(dropout),
            KANLinear(bottleneck, embedding_dim, grid_size=grid_size),
        )
        self.pathway_mixer = nn.Sequential(
            KANLinear(num_pathways, pathway_hidden, grid_size=grid_size),
            nn.Dropout(dropout),
            KANLinear(pathway_hidden, num_pathways, grid_size=grid_size),
        )
        self.output_norm = nn.LayerNorm(embedding_dim)
        self.num_pathways = num_pathways

    def forward(self, genomics: torch.Tensor) -> torch.Tensor:
        if genomics.ndim != 3 or genomics.shape[1] != self.num_pathways:
            raise ValueError(
                "genomics must be [batch, num_pathways, embedding_dim]"
            )
        encoded = self.feature_encoder(genomics)
        mixed = self.pathway_mixer(encoded.transpose(1, 2)).transpose(1, 2)
        return self.output_norm(mixed)
