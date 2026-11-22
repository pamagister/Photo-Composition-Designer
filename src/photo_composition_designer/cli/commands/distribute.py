"""Distribute command: preview or apply a distribution proposal."""

from __future__ import annotations

from photo_composition_designer.core.appdata import data_dir
from photo_composition_designer.core.errors import ProjectError
from photo_composition_designer.db.schema import WorkspaceDatabase
from photo_composition_designer.project.distribution import DistributionService


def run(
    project_id: int,
    *,
    mode: str = "slots",
    strategy: str = "equal",
    seed: int | None = None,
    best_range: str = "3-5",
    dry_run: bool = False,
) -> int:
    """Preview or apply a distribution proposal for a project."""
    database = WorkspaceDatabase(data_dir() / "workspace.sqlite3")
    try:
        distribution = DistributionService(database)
        try:
            proposal = distribution.propose(
                project_id,
                mode=mode,
                strategy=strategy,
                seed=seed,
                best_range=best_range,
            )
            summary = distribution.summarize(proposal)
            if not dry_run:
                distribution.apply(project_id, proposal)
        except (ValueError, ProjectError) as exc:
            print(f"error: {exc}")
            return 1
    finally:
        database.close()

    label = "Preview" if dry_run else "Applied"
    print(f"{label} distribution ({proposal.mode}/{proposal.strategy}, {summary.pages} page(s))")
    print(
        f"assigned {summary.assigned}, unassigned {summary.unassigned}, "
        f"overflow {summary.overflow}, not_selected {summary.not_selected}"
    )
    if summary.target is not None:
        print(f"target: {summary.target:.2f}")
    for index, group in enumerate(proposal.pages, start=1):
        print(f"  page {index}: {len(group)} photo(s)")
    if proposal.seed is not None:
        print(f"seed: {proposal.seed}")
    for warning in proposal.warnings:
        print(f"warning: {warning}")
    return 0
