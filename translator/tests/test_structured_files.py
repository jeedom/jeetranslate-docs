from pathlib import Path

from translator.structured_files import StructuredMarkdownFile, dedup_slugs, kramdown_slug


def test_kramdown_slug_matches_the_real_gem_output() -> None:
    """Values verified against the actual kramdown 2.4.0 gem with this site's GFM input
    config, not assumed."""
    assert kramdown_slug("Accès local") == "accès-local"
    assert kramdown_slug("Qu'est-ce que c'est ?") == "quest-ce-que-cest-"
    assert kramdown_slug("Étape 1 : préparation") == "étape-1--préparation"
    assert kramdown_slug("Compatibilité (matériel)") == "compatibilité-matériel"
    assert kramdown_slug("100% compatible") == "100-compatible"
    assert kramdown_slug("Résumé & synthèse") == "résumé--synthèse"
    assert kramdown_slug("Titre_avec_underscore") == "titre_avec_underscore"
    assert kramdown_slug("???") == "section"


def test_dedup_slugs_matches_kramdown_numbering() -> None:
    assert dedup_slugs(["Sauvegarde", "Restauration", "Sauvegarde", "Sauvegarde"]) == [
        "sauvegarde",
        "restauration",
        "sauvegarde-1",
        "sauvegarde-2",
    ]


def test_get_headings_returns_heading_text_in_order(tmp_path: Path) -> None:
    src_file = tmp_path / "index.md"
    src_file.write_text(
        "# Title\n"
        "\n"
        "Some prose with a [link](target.md).\n"
        "\n"
        "## Second heading\n"
        "\n"
        "```\n"
        "# not a heading, inside a code block\n"
        "```\n"
        "\n"
        "### Third heading\n",
        encoding="utf-8",
    )

    parsed_file = StructuredMarkdownFile(src_file)
    parsed_file.parse()

    assert parsed_file.get_headings() == ["Title", "Second heading", "Third heading"]
