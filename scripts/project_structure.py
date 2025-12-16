import os
import argparse
import ast
import json

# Usage with Pycharm External Tools:
# Program:     $PyInterpreterDirectory$/python
# Arguments:   $ProjectFileDir$/scripts/project_structure.py $FilePath$ --json --md --llm --doc-string
# Working dir: $ProjectFileDir$

# ─────────────────────────────────────────────────────────────
# Tree-Symbole
# ─────────────────────────────────────────────────────────────
FOLDER_SYMBOL = "📁"  # Verzeichnis
FILE_SYMBOL = "📄"  # generische Datei

PY_FILE_SYMBOL = "🐍"  # Python-Datei
SCRIPT_SYMBOL = "🖥️"  # ausführbares Script / CLI
IMAGE_SYMBOL = "🖼️"  # Bild
DOCU_SYMBOL = "📘"  # Dokumentations-Datei (html, md)

CLASS_SYMBOL = "🏛️"  # Klasse (stabile Struktur)
FUNC_SYMBOL = "⚙️"  # Funktion / Methode (Logik)
ATTR_SYMBOL = "🔹"  # Attribut / Variable


INDENT = "    "

# ─────────────────────────────────────────────────────────────
# Ignore
# ─────────────────────────────────────────────────────────────
IGNORE_DIRS = {
    ".pytest_cache",
    ".git",
    ".ruff",
    ".venv",
    ".github",
    "build",
    "dist",
    "temp",
    "info",
    "log",
    "maps",
    "collages",
    "release",
    ".idea",
    ".ruff_cache",
    "htmlcov",
    "__pycache__",
    "__main__",
    "site",
}

IGNORE_EXTENSIONS = {
    ".pyc",
    ".coverage",
    ".zip",
    ".egg-info",
    ".pre-commit-config.yaml",
    ".pre-commit-config-linux.yaml",
    ".jpg",
}


# ─────────────────────────────────────────────────────────────
# Hilfsfunktionen
# ─────────────────────────────────────────────────────────────
def should_ignore(path: str) -> bool:
    """Check if path should be ignored"""
    name = os.path.basename(path)
    if name in IGNORE_DIRS:
        return True
    if os.path.isfile(path):
        return os.path.splitext(path)[1] in IGNORE_EXTENSIONS
    return False


def visibility(name: str) -> int:
    if name.startswith("__") and not name.endswith("__"):
        return 2
    if name.startswith("_"):
        return 1
    return 0


def normalize_type(t: str | None) -> str | None:
    return t.replace("typing.", "") if t else None


def normalize_doc(doc: str | None) -> str | None:
    """Normalizes doc string: Split at first empty line and return first lines"""
    if not doc:
        return None
    return doc.strip().split("\n\n")[0]


def format_function_signature(func: ast.FunctionDef) -> str:
    args = []
    for arg in func.args.args:
        s = arg.arg
        if arg.annotation:
            s += f": {ast.unparse(arg.annotation)}"
        args.append(s)

    if func.args.vararg:
        args.append(f"*{func.args.vararg.arg}")
    if func.args.kwarg:
        args.append(f"**{func.args.kwarg.arg}")

    ret = f" -> {ast.unparse(func.returns)}" if func.returns else ""
    return f"{func.name}({', '.join(args)}){ret}"


# ─────────────────────────────────────────────────────────────
# Python-Datei → Klassenmodell
# ─────────────────────────────────────────────────────────────
def parse_python_file(path: str, include_docstrings: bool = False) -> dict:
    try:
        tree = ast.parse(open(path, encoding="utf-8").read())
    except Exception:
        return {"classes": [], "functions": []}

    classes = []
    functions = []

    for node in tree.body:
        # ── Top-Level-Funktionen ───────────────────────────
        if isinstance(node, ast.FunctionDef):
            functions.append(
                {
                    "name": node.name,
                    "signature": format_function_signature(node),
                    "visibility": "private" if node.name.startswith("_") else "public",
                    "doc": ast.get_docstring(node) if include_docstrings else None,
                }
            )

        # ── Klassen ────────────────────────────────────────
        elif isinstance(node, ast.ClassDef):
            cls = {
                "type": "class",
                "name": node.name,
                "dataclass": False,
                "doc": ast.get_docstring(node) if include_docstrings else None,
                "class_attributes": [],
                "instance_attributes": [],
                "methods": [],
            }

            for dec in node.decorator_list:
                if isinstance(dec, ast.Name) and dec.id == "dataclass":
                    cls["dataclass"] = True

            class_attrs = []
            instance_attrs = []

            for item in node.body:
                if isinstance(item, ast.FunctionDef):
                    cls["methods"].append(
                        {
                            "signature": format_function_signature(item),
                            "doc": (
                                ast.get_docstring(item) if include_docstrings else None
                            ),
                        }
                    )

                    for stmt in ast.walk(item):
                        if isinstance(stmt, ast.AnnAssign):
                            t = stmt.target
                            if (
                                isinstance(t, ast.Attribute)
                                and getattr(t.value, "id", None) == "self"
                            ):
                                instance_attrs.append(
                                    (
                                        t.attr,
                                        normalize_type(ast.unparse(stmt.annotation)),
                                    )
                                )
                        elif isinstance(stmt, ast.Assign):
                            for t in stmt.targets:
                                if (
                                    isinstance(t, ast.Attribute)
                                    and getattr(t.value, "id", None) == "self"
                                ):
                                    instance_attrs.append((t.attr, None))

                elif isinstance(item, ast.AnnAssign) and isinstance(
                    item.target, ast.Name
                ):
                    class_attrs.append(
                        (item.target.id, normalize_type(ast.unparse(item.annotation)))
                    )

                elif isinstance(item, ast.Assign):
                    for t in item.targets:
                        if isinstance(t, ast.Name):
                            class_attrs.append((t.id, None))

            # Deduplizieren
            seen = set()
            for n, t in class_attrs:
                if n not in seen:
                    cls["class_attributes"].append({"name": n, "type": t})
                    seen.add(n)

            seen.clear()
            for n, t in instance_attrs:
                if n not in seen:
                    cls["instance_attributes"].append({"name": f"self.{n}", "type": t})
                    seen.add(n)
            # sort methods by signature using visibility
            cls["methods"].sort(key=lambda x: visibility(x["signature"]))
            classes.append(cls)

    return {"classes": classes, "functions": functions}


# ─────────────────────────────────────────────────────────────
# Projektmodell
# ─────────────────────────────────────────────────────────────
def build_model(root: str, include_docstrings: bool = False) -> dict:
    node = {"type": "directory", "name": os.path.basename(root) or root, "children": []}

    try:
        if os.path.isfile(root):
            entries = [root]
        else:
            entries = sorted(os.listdir(root))
    except PermissionError:
        return node

    for e in entries:
        full = os.path.join(root, e)
        if should_ignore(full):
            continue

        if os.path.isdir(full):
            node["children"].append(
                build_model(full, include_docstrings=include_docstrings)
            )
        else:
            file_node = {"type": "file", "name": e, "classes": []}
            if e.endswith(".py"):
                parsed = parse_python_file(full, include_docstrings=include_docstrings)
                file_node["classes"] = parsed["classes"]
                file_node["functions"] = parsed["functions"]

            node["children"].append(file_node)

    return node


# ─────────────────────────────────────────────────────────────
# Renderer
# ─────────────────────────────────────────────────────────────
def render_tree(node, indent, lines):
    # symbol = FOLDER_SYMBOL if node["type"] == "directory" else FILE_SYMBOL
    if node["type"] == "directory":
        symbol = FOLDER_SYMBOL
    else:
        if node["name"].endswith(".py"):
            symbol = PY_FILE_SYMBOL
        elif node["name"].endswith(".jpg") or node["name"].endswith(".png"):
            symbol = IMAGE_SYMBOL
        elif node["name"].endswith(".sh") or node["name"].endswith(".bat"):
            symbol = SCRIPT_SYMBOL
        elif node["name"].endswith(".md") or node["name"].endswith(".html"):
            symbol = DOCU_SYMBOL
        else:
            symbol = FILE_SYMBOL

    lines.append(f"{indent}{symbol} {node['name']}")

    if node["type"] == "file":
        for fn in node.get("functions", []):
            lines.append(f"{indent}{INDENT}{FUNC_SYMBOL} {fn['signature']}")

        for cls in node["classes"]:
            lines.append(f"{indent}{INDENT}{CLASS_SYMBOL}  {cls['name']}")

            for a in cls["class_attributes"]:
                t = f": {a['type']}" if a["type"] else ""
                lines.append(f"{indent}{INDENT*2}{ATTR_SYMBOL}  {a['name']}{t}")

            for a in cls["instance_attributes"]:
                t = f": {a['type']}" if a["type"] else ""
                lines.append(f"{indent}{INDENT*2}{ATTR_SYMBOL}  {a['name']}{t}")

            for m in cls["methods"]:
                doc_str = f": {m['doc']}" if m["doc"] else ''
                lines.append(f"{indent}{INDENT*2}{FUNC_SYMBOL}  {cls['name']}.{m['signature']}{doc_str}")

    if node["type"] == "directory":
        for c in node["children"]:
            render_tree(c, indent + INDENT, lines)


def iter_files(node):
    """Generator: liefert alle File-Knoten rekursiv"""
    if node["type"] == "file":
        yield node
    elif node["type"] == "directory":
        for child in node.get("children", []):
            yield from iter_files(child)


def build_llm_summary(model, include_docstrings: bool = False) -> dict:
    modules = []

    for file_node in iter_files(model):
        if not file_node.get("classes") and not file_node.get("functions"):
            continue

        module_entry = {"module": file_node["name"], "classes": [], "functions": []}

        # ── Top-Level-Funktionen ───────────────────────────
        for fn in file_node.get("functions", []):
            if fn["visibility"] == "public":
                if include_docstrings:
                    fn["doc"] = normalize_doc(fn["doc"])
                    module_entry["functions"].append(f"{fn['signature']}: {fn['doc']}")
                else:
                    module_entry["functions"].append(fn["signature"])

        # ── Klassen ────────────────────────────────────────
        for cls in file_node.get("classes", []):
            class_entry = {
                "name": cls["name"],
                "class_attributes": [],
                "instance_attributes": [],
                "public_methods": [],
                "internal_methods": [],
            }

            for a in cls.get("class_attributes", []):
                class_entry["class_attributes"].append(
                    f"{a['name']}: {a['type']}" if a.get("type") else a["name"]
                )

            for a in cls.get("instance_attributes", []):
                class_entry["instance_attributes"].append(
                    f"{a['name']}: {a['type']}" if a.get("type") else a["name"]
                )

            for m in cls.get("methods", []):
                if m["signature"].startswith("_"):
                    class_entry["internal_methods"].append(m["signature"])
                else:
                    if include_docstrings:
                        m["doc"] = normalize_doc(m["doc"])
                        class_entry["public_methods"].append(
                            f"{m['signature']}: {m['doc']}"
                        )
                    else:
                        class_entry["public_methods"].append(m["signature"])

            module_entry["classes"].append(class_entry)

        modules.append(module_entry)

    return {"modules": modules}


def render_markdown(node, lines):
    if node["type"] == "file" and (node.get("classes") or node.get("functions")):
        file_name = os.path.basename(node["name"])
        lines.append(f"\n## File `{file_name}`\n")

        # ── Top-level functions ────────────────────────────
        if node.get("functions"):
            lines.append("### Functions")
            for fn in node["functions"]:
                lines.append(f"- `{fn['signature']}`")
                if fn.get("doc"):
                    lines.append(f"  {fn['doc']}")
            lines.append("")

        # ── Classes ─────────────────────────────────────────
        for cls in node.get("classes", []):
            lines.append(f"### Class `{cls['name']}`\n")

            # Class attributes
            if cls.get("class_attributes"):
                lines.append("**Class attributes**")
                for a in cls["class_attributes"]:
                    t = f": {a['type']}" if a.get("type") else ""
                    lines.append(f"- `{a['name']}{t}`")
                lines.append("")

            # Instance attributes
            if cls.get("instance_attributes"):
                lines.append("**Instance attributes**")
                for a in cls["instance_attributes"]:
                    name = a["name"].removeprefix("self.")
                    t = f": {a['type']}" if a.get("type") else ""
                    lines.append(f"- `{name}{t}`")
                lines.append("")

            # Methods
            if cls.get("methods"):
                lines.append("**Methods**")
                for m in cls["methods"]:
                    lines.append(f"- `{m['signature']}`")
                    if m.get("doc"):
                        lines.append(f"  {m['doc']}")
                lines.append("")

    if node["type"] == "directory":
        for c in node["children"]:
            render_markdown(c, lines)


# ─────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?", default=".")
    parser.add_argument("-m", "--md", action="store_true", help="Include markdown")
    parser.add_argument("-j", "--json", action="store_true", help="Include json")
    parser.add_argument(
        "-l", "--llm", action="store_true", help="Make the output more llm-friendly"
    )
    parser.add_argument(
        "-d",
        "--doc-string",
        action="store_true",
        help="Include docstrings in the generated output",
    )

    args = parser.parse_args()

    model = build_model(args.path, include_docstrings=args.doc_string)

    tree_lines = []
    render_tree(model, "", tree_lines)
    print("\n".join(tree_lines))

    if args.md:
        md = []
        render_markdown(model, md)
        open("project_structure.md", "w", encoding="utf-8").write("\n".join(md))

    if args.json:
        json.dump(
            model, open("project_structure.json", "w", encoding="utf-8"), indent=2
        )

    if args.llm:
        llm_json = build_llm_summary(model, include_docstrings=args.doc_string)
        json.dump(
            llm_json,
            open("project_structure_llm.json", "w", encoding="utf-8"),
            indent=2,
        )
