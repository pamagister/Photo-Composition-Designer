"""Distribute command: preview or apply a distribution proposal."""

from __future__ import annotations

from photo_composition_designer.core.appdata import data_dir
from photo_composition_designer.core.errors import ProjectError
from photo_composition_designer.db.schema import WorkspaceDatabase
from photo_composition_designer.project.distribution import DistributionService


def run(
    project_id: int,
    *,
    strategy: str = "equal",
    seed: int | None = None,
    dry_run: bool = False,
) -> int:
    """Preview or apply a distribution proposal for a project."""
    if strategy not in {"equal", "random", "date_aware"}:
        print(f"error: unknown distribution strategy: {strategy}")
        return 1
    database = WorkspaceDatabase(data_dir() / "workspace.sqlite3")
    try:
        distribution = DistributionService(database)
        try:
            proposal = distribution.propose(project_id, strategy=strategy, seed=seed)
            summary = distribution.summarize(proposal)
            if not dry_run:
                distribution.apply(project_id, proposal)
        except (ValueError, ProjectError) as exc:
            print(f"error: {exc}")
            return 1
    finally:
        database.close()

    mode = "Preview" if dry_run else "Applied"
    print(f"{mode} distribution ({proposal.strategy}, {summary.pages} page(s))")
    print(
        f"assigned {summary.assigned}, unassigned {summary.unassigned}, overflow {summary.overflow}"
    )
    for index, group in enumerate(proposal.pages, start=1):
        print(f"  page {index}: {len(group)} photo(s)")
    if proposal.seed is not None:
        print(f"seed: {proposal.seed}")
    for warning in proposal.warnings:
        print(f"warning: {warning}")
    return 0
