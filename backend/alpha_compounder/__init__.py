"""
Alpha Compounder Discovery — Multi-Agent Attribution Pipeline
==============================================================
Retrospective causal attribution over outlier price runs,
with adversarial hypothesis refinement and regime-conditional
forward strategy synthesis.

Package layout:
  config.py          Grid cells, priors, budget defaults
  schemas.py         Pydantic models for all shared schemas
  factor_catalog.py  Factor definitions + family gating
  factor_service.py  FactorService — shared compute engine
  gcs_io.py          GCS read/write helpers
  utils.py           PIT helpers, overlap resolution

  agent_a/           Run Discovery
  orchestrator/      B↔C adversarial loop
  agents/            LLM-bound attribution agents
  agent_d/           Strategy synthesis
"""

__version__ = "0.1.0"
