from pathlib import Path

import pytest

from translator.consts import (
    FR_FR,
    ALL_LANGUAGES
)
from translator.structured_files import StructuredMarkdownFile
from translator.translator import Translator


def test_docs_translator_init_minimal(tmp_path: Path) -> None:
    translator = Translator(
        deepl_api_key="dummy-key",
        target_languages=ALL_LANGUAGES,
        cwd=tmp_path
    )

    assert translator is not None
    assert isinstance(translator, Translator)


def test_start_returns_zero_when_source_folder_missing(tmp_path: Path, caplog) -> None:
    translator = Translator(
        deepl_api_key="dummy-key",
        target_languages=ALL_LANGUAGES,
        cwd=tmp_path
    )

    result = translator.start()

    assert result == 0
    assert "nothing to do." in caplog.text


def test_multiple_docs_roots_require_memory_path(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="memory_path is required when multiple docs_roots are configured"):
        Translator(
            deepl_api_key="dummy-key",
            target_languages=ALL_LANGUAGES,
            cwd=tmp_path,
            docs_roots=["docs", "plugins/docs"],
        )


def test_process_file_preserves_front_matter_keys_and_updates_lang(tmp_path: Path) -> None:
    translator = Translator(
        deepl_api_key="dummy-key",
        target_languages=ALL_LANGUAGES,
        cwd=tmp_path
    )
    mapping = {
        "Bonjour": "Hola",
        "Documentation Arlo": "Documentación Arlo"
    }

    translator._deepl_translate = lambda target_lang, texts: [mapping[t] for t in texts]

    src_root = tmp_path / "docs" / FR_FR
    target_root = tmp_path / "docs" / "es_ES"
    src_root.mkdir(parents=True)

    src_file = src_root / "index.md"
    target_file = target_root / "index.md"
    src_file.write_text(
        "---\n"
        "layout: default\n"
        "title: Documentation Arlo\n"
        "lang: fr_FR\n"
        "pluginId: arlo\n"
        "---\n"
        "\n"
        "# Bonjour\n",
        encoding="utf-8",
    )

    parsed_file = StructuredMarkdownFile(src_file)
    parsed_file.parse()

    translator._write_target_file(parsed_file, "es_ES", target_file)

    assert target_file.read_text(encoding="utf-8") == (
        "---\n"
        "layout: default\n"
        "title: Documentación Arlo\n"
        "lang: es_ES\n"
        "pluginId: arlo\n"
        "---\n"
        "\n"
        "# Hola\n"
    )


def test_start_translates_nested_source_language_directories(tmp_path: Path) -> None:
    """Files in nested fr_FR directories (e.g. plugin1/fr_FR and plugin1/beta/fr_FR)
    are both discovered and translated, with the target placed in the same structure."""
    translator = Translator(
        deepl_api_key="dummy-key",
        target_languages=["en_US"],
        cwd=tmp_path,
        docs_roots=["docs"],
        memory_path=str(tmp_path / "memory.json"),
    )

    mapping = {"Bonjour": "Hello", "Beta": "Beta"}
    translator._deepl_translate = lambda target_lang, texts: [mapping[t] for t in texts]

    # plugin1/fr_FR/index.md
    src1 = tmp_path / "docs" / "plugin1" / FR_FR
    src1.mkdir(parents=True)
    (src1 / "index.md").write_text("# Bonjour\n", encoding="utf-8")

    # plugin1/beta/fr_FR/index.md
    src2 = tmp_path / "docs" / "plugin1" / "beta" / FR_FR
    src2.mkdir(parents=True)
    (src2 / "index.md").write_text("# Beta\n", encoding="utf-8")

    result = translator.start()

    assert result == 0

    target1 = tmp_path / "docs" / "plugin1" / "en_US" / "index.md"
    assert target1.exists(), "Expected translated file at plugin1/en_US/index.md"
    assert target1.read_text(encoding="utf-8") == "# Hello\n"

    target2 = tmp_path / "docs" / "plugin1" / "beta" / "en_US" / "index.md"
    assert target2.exists(), "Expected translated file at plugin1/beta/en_US/index.md"
    assert target2.read_text(encoding="utf-8") == "# Beta\n"


def test_process_file_protects_link_target_embedded_mid_sentence(tmp_path: Path) -> None:
    """A markdown link embedded in the middle of a sentence (not alone on its own line)
    must keep its target and anchor untouched: DeepL only ever sees the link's label and
    the surrounding prose, never the URL."""
    translator = Translator(
        deepl_api_key="dummy-key",
        target_languages=ALL_LANGUAGES,
        cwd=tmp_path
    )
    mapping = {
        "Consulter la documentation relative à la ": "Refer to the documentation on ",
        "**première connexion**": "**first-time login**",
        " pour accéder à l'interface Jeedom suite à l'installation.": " to access the Jeedom interface after installation.",
    }
    translator._deepl_translate = lambda target_lang, texts: [mapping[t] for t in texts]

    src_root = tmp_path / "docs" / FR_FR
    target_root = tmp_path / "docs" / "en_US"
    src_root.mkdir(parents=True)

    src_file = src_root / "index.md"
    target_file = target_root / "index.md"
    src_file.write_text(
        "Consulter la documentation relative à la [**première connexion**](/premiers-pas/#Première%20connexion) pour accéder à l'interface Jeedom suite à l'installation.\n",
        encoding="utf-8",
    )

    parsed_file = StructuredMarkdownFile(src_file)
    parsed_file.parse()

    translator._write_target_file(parsed_file, "en_US", target_file)

    assert target_file.read_text(encoding="utf-8") == (
        "Refer to the documentation on [**first-time login**](/premiers-pas/#Première%20connexion) to access the Jeedom interface after installation.\n"
    )


def test_process_file_excludes_liquid_tag_from_translation(tmp_path: Path) -> None:
    """A Jekyll/Liquid tag (e.g. an image include with a src path) is a template directive,
    not prose: it must never be sent to DeepL, so a filename that happens to look like French
    words can't get mistranslated."""
    translator = Translator(
        deepl_api_key="dummy-key",
        target_languages=ALL_LANGUAGES,
        cwd=tmp_path
    )

    def fail_if_called(target_lang, texts):
        raise AssertionError(f"DeepL should not be called for a Liquid tag line, got: {texts}")

    translator._deepl_translate = fail_if_called

    src_root = tmp_path / "docs" / FR_FR
    target_root = tmp_path / "docs" / "en_US"
    src_root.mkdir(parents=True)

    src_file = src_root / "index.md"
    target_file = target_root / "index.md"
    line = '{% include lightbox.html src="../images/tableau-comparatif-atlas-et-luna.jpg" title="Jeedom Atlas & Jeedom Luna" %}\n'
    src_file.write_text(line, encoding="utf-8")

    parsed_file = StructuredMarkdownFile(src_file)
    parsed_file.parse()

    translator._write_target_file(parsed_file, "en_US", target_file)

    assert target_file.read_text(encoding="utf-8") == line


def test_process_file_excludes_html_only_line_from_translation(tmp_path: Path) -> None:
    """A line that is pure HTML markup with no real prose (e.g. a search bar placeholder div)
    must not be sent to DeepL at all."""
    translator = Translator(
        deepl_api_key="dummy-key",
        target_languages=ALL_LANGUAGES,
        cwd=tmp_path
    )

    def fail_if_called(target_lang, texts):
        raise AssertionError(f"DeepL should not be called for a markup-only line, got: {texts}")

    translator._deepl_translate = fail_if_called

    src_root = tmp_path / "docs" / FR_FR
    target_root = tmp_path / "docs" / "en_US"
    src_root.mkdir(parents=True)

    src_file = src_root / "index.md"
    target_file = target_root / "index.md"
    line = '<div id="div_searchBar"></div>\n'
    src_file.write_text(line, encoding="utf-8")

    parsed_file = StructuredMarkdownFile(src_file)
    parsed_file.parse()

    translator._write_target_file(parsed_file, "en_US", target_file)

    assert target_file.read_text(encoding="utf-8") == line


def test_process_file_translates_text_between_html_tags(tmp_path: Path) -> None:
    """Real prose sitting between HTML tags is still translated; only the tags themselves
    are protected."""
    translator = Translator(
        deepl_api_key="dummy-key",
        target_languages=ALL_LANGUAGES,
        cwd=tmp_path
    )
    mapping = {
        "Bonjour": "Hello",
        " le monde.": " world.",
    }
    translator._deepl_translate = lambda target_lang, texts: [mapping[t] for t in texts]

    src_root = tmp_path / "docs" / FR_FR
    target_root = tmp_path / "docs" / "en_US"
    src_root.mkdir(parents=True)

    src_file = src_root / "index.md"
    target_file = target_root / "index.md"
    src_file.write_text("<strong>Bonjour</strong> le monde.\n", encoding="utf-8")

    parsed_file = StructuredMarkdownFile(src_file)
    parsed_file.parse()

    translator._write_target_file(parsed_file, "en_US", target_file)

    assert target_file.read_text(encoding="utf-8") == "<strong>Hello</strong> world.\n"


def test_process_file_protects_bare_url_in_prose(tmp_path: Path) -> None:
    """A URL typed directly in prose, with no markdown/HTML wrapping at all, must still
    never be sent to DeepL."""
    translator = Translator(
        deepl_api_key="dummy-key",
        target_languages=ALL_LANGUAGES,
        cwd=tmp_path
    )
    mapping = {
        "Puis rendez-vous sur ": "Then go to ",
    }
    translator._deepl_translate = lambda target_lang, texts: [mapping[t] for t in texts]

    src_root = tmp_path / "docs" / FR_FR
    target_root = tmp_path / "docs" / "en_US"
    src_root.mkdir(parents=True)

    src_file = src_root / "index.md"
    target_file = target_root / "index.md"
    src_file.write_text("- Puis rendez-vous sur http://jeedomatlasrecovery.local/\n", encoding="utf-8")

    parsed_file = StructuredMarkdownFile(src_file)
    parsed_file.parse()

    translator._write_target_file(parsed_file, "en_US", target_file)

    assert target_file.read_text(encoding="utf-8") == "- Then go to http://jeedomatlasrecovery.local/\n"


def test_process_file_protects_url_inside_double_backtick_code_span(tmp_path: Path) -> None:
    """A URL wrapped in a double-backtick inline code span must never be sent to DeepL,
    even though it contains no markdown link syntax; the surrounding prose is still translated."""
    translator = Translator(
        deepl_api_key="dummy-key",
        target_languages=ALL_LANGUAGES,
        cwd=tmp_path
    )
    mapping = {
        "Serveur:Port : ": "Server:Port: ",
    }
    translator._deepl_translate = lambda target_lang, texts: [mapping[t] for t in texts]

    src_root = tmp_path / "docs" / FR_FR
    target_root = tmp_path / "docs" / "en_US"
    src_root.mkdir(parents=True)

    src_file = src_root / "index.md"
    target_file = target_root / "index.md"
    src_file.write_text("-   Serveur:Port : ``https://mondomain.tld``\n", encoding="utf-8")

    parsed_file = StructuredMarkdownFile(src_file)
    parsed_file.parse()

    translator._write_target_file(parsed_file, "en_US", target_file)

    assert target_file.read_text(encoding="utf-8") == "-   Server:Port: ``https://mondomain.tld``\n"


def test_process_file_does_not_translate_link_label_that_is_itself_a_url(tmp_path: Path) -> None:
    """When a link's visible label is itself a bare URL (e.g. the link target repeated as
    its own display text), that label must not be sent to DeepL either."""
    translator = Translator(
        deepl_api_key="dummy-key",
        target_languages=ALL_LANGUAGES,
        cwd=tmp_path
    )
    # Only the text before the link is a genuine translatable string; if the URL-as-label
    # were (incorrectly) sent too, the lookup below would raise a KeyError.
    mapping = {"| **Smart** | ": "| **Smart** | "}
    translator._deepl_translate = lambda target_lang, texts: [mapping[t] for t in texts]

    src_root = tmp_path / "docs" / FR_FR
    target_root = tmp_path / "docs" / "en_US"
    src_root.mkdir(parents=True)

    src_file = src_root / "index.md"
    target_file = target_root / "index.md"
    line = '| **Smart** | [http://jeedomsmart.local](http://jeedomsmart.local){:target="_blank"} |\n'
    src_file.write_text(line, encoding="utf-8")

    parsed_file = StructuredMarkdownFile(src_file)
    parsed_file.parse()

    translator._write_target_file(parsed_file, "en_US", target_file)

    assert target_file.read_text(encoding="utf-8") == line


def test_process_file_translates_only_the_alt_text_of_a_clickable_image(tmp_path: Path) -> None:
    """A clickable image ([![alt](image_target)](link_target), e.g. an app-store badge or a
    video thumbnail) must only expose the alt text to DeepL: nested brackets previously made
    the leading '![' of the inner image leak into what was sent for translation."""
    translator = Translator(
        deepl_api_key="dummy-key",
        target_languages=ALL_LANGUAGES,
        cwd=tmp_path
    )
    mapping = {"Disassembly/reassembly video": "Disassembly/reassembly video"}
    translator._deepl_translate = lambda target_lang, texts: [mapping[t] for t in texts]

    src_root = tmp_path / "docs" / FR_FR
    target_root = tmp_path / "docs" / "en_US"
    src_root.mkdir(parents=True)

    src_file = src_root / "index.md"
    target_file = target_root / "index.md"
    line = '[![Disassembly/reassembly video](https://img.youtube.com/vi/abc123/hqdefault.jpg)](https://youtu.be/abc123){:target="_blank"}\n'
    src_file.write_text(line, encoding="utf-8")

    parsed_file = StructuredMarkdownFile(src_file)
    parsed_file.parse()

    translator._write_target_file(parsed_file, "en_US", target_file)

    assert target_file.read_text(encoding="utf-8") == line


def test_process_file_localizes_only_doc_site_links(tmp_path: Path) -> None:
    """A doc.jeedom.com or docs-root relative link hardcoded to fr_FR must point to the
    output language instead; a link to another host must stay untouched, including a GitHub
    source URL whose path happens to contain a docs root followed by fr_FR."""
    translator = Translator(
        deepl_api_key="dummy-key",
        target_languages=ALL_LANGUAGES,
        cwd=tmp_path
    )
    translator._deepl_translate = lambda target_lang, texts: list(texts)

    src_root = tmp_path / "docs" / FR_FR
    target_root = tmp_path / "docs" / "en_US"
    src_root.mkdir(parents=True)

    src_file = src_root / "index.md"
    target_file = target_root / "index.md"
    src_file.write_text(
        "https://doc.jeedom.com/contribute/fr_FR/beta\n"
        "https://mondomain.tld/fr_FR/page\n"
        "[Recovery](/docs/fr_FR/recovery.md)\n"
        "[Elsewhere](/notaroot/fr_FR/page.md)\n"
        "[docs/fr_FR/recovery.md](https://github.com/jeedom/documentations/blob/master/docs/fr_FR/recovery.md)\n",
        encoding="utf-8",
    )

    parsed_file = StructuredMarkdownFile(src_file)
    parsed_file.parse()

    translator._write_target_file(parsed_file, "en_US", target_file)

    assert target_file.read_text(encoding="utf-8") == (
        "https://doc.jeedom.com/contribute/en_US/beta\n"
        "https://mondomain.tld/fr_FR/page\n"
        "[Recovery](/docs/en_US/recovery.md)\n"
        "[Elsewhere](/notaroot/fr_FR/page.md)\n"
        "[docs/fr_FR/recovery.md](https://github.com/jeedom/documentations/blob/master/docs/fr_FR/recovery.md)\n"
    )


def test_start_localizes_link_anchors(tmp_path: Path) -> None:
    """A link's #anchor is rewritten to the target heading's translated, kramdown-slugified id:
    cross-file, same-page, external link untouched, and a heading with inline code (must stay
    out of translation like regular prose)."""
    translator = Translator(
        deepl_api_key="dummy-key",
        target_languages=["en_US"],
        cwd=tmp_path,
        docs_roots=["installation", "premiers-pas"],
        memory_path=str(tmp_path / "memory.json"),
    )
    mapping = {"Accès local": "Local access", "ici": "here", "ailleurs": "elsewhere", "Liste ": "List ", "lien": "link"}
    translator._deepl_translate = lambda target_lang, texts: [mapping[t] for t in texts]

    pp_src = tmp_path / "premiers-pas" / FR_FR
    pp_src.mkdir(parents=True)
    (pp_src / "index.md").write_text("# Accès local\n", encoding="utf-8")

    inst_src = tmp_path / "installation" / FR_FR
    inst_src.mkdir(parents=True)
    (inst_src / "recovery.md").write_text(
        "# Accès local\n"
        "[ici](../../premiers-pas/fr_FR/index.md#accès-local)\n"
        "[ici](#accès-local)\n"
        "[ailleurs](https://example.com/page#accès-local)\n"
        "## Liste ``info.json``\n"
        "[lien](#liste-infojson)\n",
        encoding="utf-8",
    )

    result = translator.start()
    assert result == 0

    target = tmp_path / "installation" / "en_US" / "recovery.md"
    assert target.read_text(encoding="utf-8") == (
        "# Local access\n"
        "[here](../../premiers-pas/en_US/index.md#local-access)\n"
        "[here](#local-access)\n"
        "[elsewhere](https://example.com/page#accès-local)\n"
        "## List ``info.json``\n"
        "[link](#list-infojson)\n"
    )
