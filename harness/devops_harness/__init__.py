"""devops-harness — project infrastructure forging + task execution framework.

Two sub-packages:
  - creator:  Scan project → generate harness infrastructure (AGENTS.md, docs, linters, CI)
  - executor: Execute tasks → self-validate → verify → record
"""
from devops_harness.creator import HarnessCreator
from devops_harness.executor import HarnessExecutor

__all__ = ["HarnessCreator", "HarnessExecutor"]
__version__ = "0.1.0"
