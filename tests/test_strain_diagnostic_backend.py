"""Ensure experimental strain reporting does not hide a backend ratio veto."""
import numpy as np
from src.posterior_deformation import _embedded_arap_posterior


def test_supported_expansion_can_pass_both_solver_levels_without_ratio_veto():
    x,y=np.meshgrid(np.linspace(-.5,.5,14),np.linspace(-.5,.5,14))
    prior=np.c_[x.ravel(),y.ravel(),.02*np.sin(x.ravel())]
    target=prior*1.7
    options=dict(node_fraction=.2,minimum_nodes=32,maximum_nodes=256,skinning_neighbours=4,
                 neighbours=10,edge_ratio=2.5,attachment_edge_ratio=3.2,
                 data_weight=100.,screening=.001,iterations=3,maximum_displacement=2.,
                 minimum_improvement=.01,minimum_edge_compression=.99,maximum_edge_stretch=1.01,
                 minimum_hidden_coverage=.5,coverage_resolution=64,
                 coherent_component_targets=False,hard_target_constraints=True)
    strict,strict_info,_=_embedded_arap_posterior(prior,np.arange(len(prior)),target,np.ones(len(prior)),np.zeros(len(prior),bool),**options)
    relaxed,info,_=_embedded_arap_posterior(prior,np.arange(len(prior)),target,np.ones(len(prior)),np.zeros(len(prior),bool),enforce_edge_strain_limits=False,**options)
    assert not strict_info['active']
    assert info['active']
    assert np.mean(np.linalg.norm(relaxed-target,axis=1))<np.mean(np.linalg.norm(strict-target,axis=1))
    assert relaxed.shape==prior.shape and np.isfinite(relaxed).all()
