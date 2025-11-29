<!-- This README.md is auto-generated from docs/index.md -->

# Welcome to Photo-Composition-Designer

A feature-rich Python project template with auto-generated CLI, GUI and parameterized configuration.

[![Github CI Status](https://github.com/pamagister/Photo-Composition-Designer/actions/workflows/main.yml/badge.svg)](https://github.com/pamagister/Photo-Composition-Designer/actions)
[![GitHub release](https://img.shields.io/github/v/release/pamagister/Photo-Composition-Designer)](https://github.com/pamagister/Photo-Composition-Designer/releases)
[![Read the Docs](https://readthedocs.org/projects/Photo-Composition-Designer/badge/?version=stable)](https://Photo-Composition-Designer.readthedocs.io/en/stable/)
[![License](https://img.shields.io/github/license/pamagister/Photo-Composition-Designer)](https://github.com/pamagister/Photo-Composition-Designer/blob/main/LICENSE)
[![GitHub issues](https://img.shields.io/github/issues/pamagister/Photo-Composition-Designer)](https://github.com/pamagister/Photo-Composition-Designer/issues)
[![PyPI](https://img.shields.io/pypi/v/Photo-Composition-Designer)](https://pypi.org/project/Photo-Composition-Designer/)
[![Downloads](https://pepy.tech/badge/Photo-Composition-Designer)](https://pepy.tech/project/Photo-Composition-Designer/)


---


## Installation

Get an impression of how your own project could be installed and look like.

Download from [PyPI](https://pypi.org/).

💾 For more installation options see [install](docs/getting-started/install.md).

```bash
pip install Photo-Composition-Designer
```

Run GUI from command line

```bash
Photo-Composition-Designer-gui
```

Run application from command line using CLI

```bash
python -m Photo_Composition_Designer.cli [OPTIONS] path/to/file
```

```bash
Photo-Composition-Designer-cli [OPTIONS] path/to/file
```

---

## Troubleshooting

### Problems with release pipeline

If you get this error below:
```bash
/home/runner/work/_temp/xxxx_xxx.sh: line 1: .github/release_message.sh: Permission denied
```

You have to run these commands in your IDE Terminal or the git bash and then push the changes.
```bash
git update-index --chmod=+x ./.github/release_message.sh
```

