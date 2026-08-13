"""Unit tests for MorningBriefGenerator end-to-end file output."""

from __future__ import annotations

from pathlib import Path

from app.agents.morning_brief_generator.data_preparation import prepare_brief_data
from app.agents.morning_brief_generator.formatter import render_markdown
from app.agents.morning_brief_generator.generator import MorningBriefGenerator
from app.schemas.intelligence import MorningIntelligence


def test_generate_writes_expected_file(
    tmp_path: Path, sample_intelligence: MorningIntelligence
) -> None:
    generator = MorningBriefGenerator(output_dir=tmp_path)

    output_path = generator.generate(sample_intelligence)

    assert output_path.exists()
    assert output_path.name == "morning-brief-2026-08-03.md"
    assert output_path.parent == tmp_path


def test_generated_file_content_matches_formatter_output(
    tmp_path: Path, sample_intelligence: MorningIntelligence
) -> None:
    generator = MorningBriefGenerator(output_dir=tmp_path)

    output_path = generator.generate(sample_intelligence)

    expected = render_markdown(prepare_brief_data(sample_intelligence))
    assert output_path.read_text(encoding="utf-8") == expected


def test_generate_creates_output_dir_if_missing(
    tmp_path: Path, sample_intelligence: MorningIntelligence
) -> None:
    nested_dir = tmp_path / "nested" / "reports"
    generator = MorningBriefGenerator(output_dir=nested_dir)

    output_path = generator.generate(sample_intelligence)

    assert nested_dir.exists()
    assert output_path.exists()
