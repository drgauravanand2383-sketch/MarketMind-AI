"""Top-level orchestration for producing a Morning Brief markdown file.

MorningBriefGenerator ties together data preparation and formatting, then
writes the result to disk. It contains no formatting or ordering logic of
its own — both are delegated to data_preparation and formatter.
"""

from __future__ import annotations

from pathlib import Path

from app.agents.morning_brief_generator.data_preparation import prepare_brief_data
from app.agents.morning_brief_generator.formatter import render_markdown
from app.schemas.intelligence import MorningIntelligence

__all__ = ["DEFAULT_OUTPUT_DIR", "MorningBriefGenerator"]

DEFAULT_OUTPUT_DIR = Path("data/reports")


class MorningBriefGenerator:
    """Produces a deterministic Markdown Morning Brief from normalized intelligence.

    This class performs no data preparation or formatting itself; it
    delegates to `data_preparation.prepare_brief_data` and
    `formatter.render_markdown` and is responsible only for writing the
    result to disk.
    """

    def __init__(self, output_dir: Path = DEFAULT_OUTPUT_DIR) -> None:
        """Initialize the generator.

        Args:
            output_dir: Directory the generated markdown file is written to.
        """
        self._output_dir = output_dir

    def generate(self, intelligence: MorningIntelligence) -> Path:
        """Prepare, render, and persist a Morning Brief for the given intelligence.

        Args:
            intelligence: Normalized intelligence object to render.

        Returns:
            The path of the written markdown file.
        """
        render_data = prepare_brief_data(intelligence)
        markdown = render_markdown(render_data)

        self._output_dir.mkdir(parents=True, exist_ok=True)
        output_path = self._output_dir / f"morning-brief-{render_data.report_date}.md"
        output_path.write_text(markdown, encoding="utf-8")
        return output_path
