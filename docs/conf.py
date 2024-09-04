# Configuration file for the Sphinx documentation builder.
#
# This file only contains a selection of the most common options. For a full
# list see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

import pathlib

# -- Project information -----------------------------------------------------
project = "py2spack"
author = "David Hofer"

version = ""
try:
    with open(pathlib.Path(__file__).parent / ".." / "src" / "py2spack" / "__init__.py") as f:
        for line in f:
            if line.startswith("__version__"):
                exec(line, ctx:={})
                version = ctx["__version__"]
                break
except:
    version = ""

master_doc = "index"
language = "en"

# -- General configuration ---------------------------------------------------
# Add any Sphinx extension module names here, as strings. They can be
# extensions coming with Sphinx (named 'sphinx.ext.*') or your custom
# ones.
extensions = [
    "myst_parser",
    "autodoc2",
    "sphinx.ext.intersphinx",
    "sphinx.ext.viewcode",
    "sphinx.ext.autosummary",
    # disabled due to https://github.com/mgaitan/sphinxcontrib-mermaid/issues/109
    # "sphinxcontrib.mermaid",
]

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
# This pattern also affects html_static_path and html_extra_path.
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

suppress_warnings = ["myst.strikethrough"]

intersphinx_mapping = {
    "packaging": ("https://packaging.pypa.io/en/stable", None),
    "python": ("https://docs.python.org/3.10", None),
    "spack": ("https://spack.readthedocs.io/en/latest", None),
    "sphinx": ("https://www.sphinx-doc.org/en/master", None),
}

# -- Autodoc2 settings ---------------------------------------------------
autodoc2_packages = [
    {
        "path": "../src/py2spack",
        "exclude_files": ["_docs.py"],
    }
]
autodoc2_hidden_objects = ["dunder", "private", "inherited"]
autodoc2_replace_annotations = [
    ("re.Pattern", "typing.Pattern"),
    ("markdown_it.MarkdownIt", "markdown_it.main.MarkdownIt"),
]
autodoc2_replace_bases = [
    ("sphinx.directives.SphinxDirective", "sphinx.util.docutils.SphinxDirective"),
]
autodoc2_docstring_parser_regexes = [
    ("myst_parser", "myst"),
    (r"myst_parser\.setup", "myst"),
]
nitpicky = True
# nitpick_ignore_regex = [
#     (r"py:.*", r"docutils\..*"),
#     (r"py:.*", r"pygments\..*"),
#     (r"py:.*", r"typing\.Literal\[.*"),
# ]
# nitpick_ignore = [
#     ("py:obj", "myst_parser._docs._ConfigBase"),
#     ("py:exc", "MarkupError"),
#     ("py:class", "sphinx.util.typing.Inventory"),
#     ("py:class", "sphinx.writers.html.HTMLTranslator"),
#     ("py:obj", "sphinx.transforms.post_transforms.ReferencesResolver"),
# ]

# -- MyST settings ---------------------------------------------------
myst_enable_extensions = [
    "dollarmath",
    "amsmath",
    "deflist",
    "fieldlist",
    "html_admonition",
    "html_image",
    "colon_fence",
    "smartquotes",
    "replacements",
    "linkify",
    "strikethrough",
    "substitution",
    "tasklist",
    "attrs_inline",
    "attrs_block",
]
myst_url_schemes = {
    "http": None,
    "https": None,
    "mailto": None,
    "ftp": None,
    "wiki": "https://en.wikipedia.org/wiki/{{path}}#{{fragment}}",
    "doi": "https://doi.org/{{path}}",
}
myst_number_code_blocks = ["typescript"]
myst_heading_anchors = 2
myst_footnote_transition = True
myst_dmath_double_inline = True
myst_enable_checkboxes = True
myst_substitutions = {
    "role": "[role](#syntax/roles)",
    "directive": "[directive](#syntax/directives)",
}

# -- HTML output -------------------------------------------------
html_theme = "sphinx_book_theme"
html_logo = "_static/images/spack-logo-white.svg"
html_favicon = "_static/images/favicon.ico"
html_title = ""
html_theme_options = {
    "home_page_in_toc": True,
    # "github_url": "https://github.com/executablebooks/MyST-Parser",
    "repository_url": "https://github.com/davhofer/py2spack",
    "repository_branch": "main",
    "path_to_docs": "docs",
    "use_repository_button": True,
    "use_edit_page_button": True,
    "use_issues_button": True,
    # "announcement": "<b>v3.0.0</b> is now out! See the Changelog for details",
}
html_last_updated_fmt = ""

# Add any paths that contain custom static files (such as style sheets) here,
# relative to this directory. They are copied after the builtin static files,
# so a file named "default.css" will overwrite the builtin "default.css".
html_static_path = ["_static"]

tippy_skip_anchor_classes = ("headerlink", "sd-stretched-link", "sd-rounded-pill")
tippy_anchor_parent_selector = "article.bd-article"
tippy_rtd_urls = [
    "https://www.sphinx-doc.org/en/master",
    "https://markdown-it-py.readthedocs.io/en/latest",
]

# -- LaTeX output -------------------------------------------------
latex_engine = "xelatex"

# -- Local Sphinx extensions -------------------------------------------------
