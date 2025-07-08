"""CLI entry point for uab_scholars package."""
from __future__ import annotations

import json
import sys
from typing import Optional, List

import click

from .client import ScholarsClient

client = ScholarsClient()


@click.group()
def main() -> None:
    """UAB Scholars lookup command-line tool."""
    pass


@main.command("search")
@click.argument("name")
@click.option("--department", "-d", help="Filter by department name substring.")
def search_cmd(name: str, department: Optional[str]) -> None:
    """Search for a scholar by NAME (quoted string)."""
    import asyncio

    async def _run():
        res_json = await client.search_scholars(name, department=department)
        data = json.loads(res_json)
        click.echo(json.dumps(data, indent=2))

    asyncio.run(_run())


@main.command("department")
@click.argument("dept", metavar="DEPARTMENT")
@click.option("--max", "max_results", default=25, help="Maximum faculty to list", show_default=True)
def department_cmd(dept: str, max_results: int) -> None:
    """List faculty in DEPARTMENT (exact string as used in API)."""
    import asyncio

    async def _run():
        res_json = await client.search_by_department(dept)
        data = json.loads(res_json)
        people: List[dict] = data.get("results", [])[:max_results]
        for p in people:
            click.echo(f"{p['profile']['name']} – {p['profile']['url']}")
        click.echo(f"\nTotal returned: {len(data.get('results', []))}")

    asyncio.run(_run())


if __name__ == "__main__":
    main() 