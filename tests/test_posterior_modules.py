"""Architectural contracts for the modular posterior implementation."""

from __future__ import annotations

from src.carrier_protection import project_reference_carrier_protection
from src.partial_transport import partial_optimal_transport
from src.posterior_adapter import PosteriorAdapter, PosteriorAdapterConfig
from src.posterior_deformation import _embedded_arap_posterior


def test_public_facade_keeps_historical_entrypoints():
    from src import posterior_adapter as facade

    assert facade.PosteriorAdapter is PosteriorAdapter
    assert facade.PosteriorAdapterConfig is PosteriorAdapterConfig
    assert facade.partial_optimal_transport is partial_optimal_transport
    assert facade._embedded_arap_posterior is _embedded_arap_posterior
    assert facade.project_reference_carrier_protection is project_reference_carrier_protection


def test_default_configuration_is_dataset_independent():
    config = PosteriorAdapterConfig()
    config.validate()
    serialized = vars(config)
    forbidden = {"sample", "category", "class_name", "part", "redwood", "custom"}
    assert forbidden.isdisjoint(serialized)
