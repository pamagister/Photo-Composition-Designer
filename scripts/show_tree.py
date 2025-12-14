import os
import argparse
import ast
import json

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
def parse_python_file(path: str) -> dict:
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
                    "visibility": (
                        "private" if node.name.startswith("_") else "public"
                    ),
                }
            )

        # ── Klassen ────────────────────────────────────────
        elif isinstance(node, ast.ClassDef):
            cls = {
                "type": "class",
                "name": node.name,
                "dataclass": False,
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
                    cls["methods"].append(format_function_signature(item))

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

            cls["methods"].sort(key=visibility)
            classes.append(cls)

    return {"classes": classes, "functions": functions}


# ─────────────────────────────────────────────────────────────
# Projektmodell
# ─────────────────────────────────────────────────────────────
def build_model(root: str) -> dict:
    node = {"type": "directory", "name": os.path.basename(root) or root, "children": []}

    try:
        entries = sorted(os.listdir(root))
    except PermissionError:
        return node

    for e in entries:
        full = os.path.join(root, e)
        if should_ignore(full):
            continue

        if os.path.isdir(full):
            node["children"].append(build_model(full))
        else:
            file_node = {"type": "file", "name": e, "classes": []}
            if e.endswith(".py"):
                parsed = parse_python_file(full)
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
                lines.append(f"{indent}{INDENT*2}{FUNC_SYMBOL}  {cls['name']}.{m}")

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


def build_llm_summary(model) -> dict:
    modules = []

    for file_node in iter_files(model):
        if not file_node.get("classes"):
            continue

        module_entry = {"module": file_node["name"], "classes": []}

        for cls in file_node["classes"]:
            class_entry = {
                "name": cls["name"],
                "class_attributes": [
                    a["name"] for a in cls.get("class_attributes", [])
                ],
                "instance_attributes": [
                    a["name"].removeprefix("self.")
                    for a in cls.get("instance_attributes", [])
                ],
                "public_methods": [
                    m for m in cls.get("methods", []) if not m.startswith("_")
                ],
                "internal_methods": [
                    m for m in cls.get("methods", []) if m.startswith("_")
                ],
            }

            module_entry["classes"].append(class_entry)
            module_entry["functions"] = [
                fn["name"]
                for fn in file_node.get("functions", [])
                if fn["visibility"] == "public"
            ]

        modules.append(module_entry)

    return {"modules": modules}


def render_markdown(node, lines):
    if node["type"] == "file" and node["classes"]:
        lines.append(f"\n## File `{node['name']}`\n")

        if node.get("functions"):
            lines.append("### Functions")
            for fn in node["functions"]:
                lines.append(f"- `{fn['signature']}`")

        for cls in node["classes"]:
            lines.append(f"### Class `{cls['name']}`")

            first = True
            for a in cls["class_attributes"]:
                if first:
                    lines.append(f"\n**Class attributes of `{cls['name']}`**\n")
                t = f": {a['type']}" if a["type"] else ""
                lines.append(f"- `{a['name']}{t}`")
                first = False

            first = True
            for a in cls["instance_attributes"]:
                if first:
                    lines.append(f"\n**Instance attributes of `{cls['name']}`**\n")
                t = f": {a['type']}" if a["type"] else ""
                lines.append(f"- `{a['name']}{t}`")
                first = False

            first = True
            for m in cls["methods"]:
                if first:
                    lines.append(f"\n**Methods of `{cls['name']}`**\n")
                lines.append(f"- `{m}`")
                first = False

    if node["type"] == "directory":
        for c in node["children"]:
            render_markdown(c, lines)


# ─────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?", default=".")
    parser.add_argument("--md", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--llm", action="store_true")

    args = parser.parse_args()

    model = build_model(args.path)

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

    if True or args.llm:
        llm_json = build_llm_summary(model)
        json.dump(
            llm_json,
            open("project_structure_llm.json", "w", encoding="utf-8"),
            indent=2,
        )
