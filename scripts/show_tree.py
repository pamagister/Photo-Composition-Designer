import os
import argparse
import ast
import inspect

# Symbole
FOLDER_SYMBOL = "[D]"
FILE_SYMBOL = "[F]"
CLASS_SYMBOL = "[C]"
FUNC_SYMBOL = "[M]"
ATTR_SYMBOL = "[A]"
BRANCH = "|-- "
LAST_BRANCH = "`-- "
VERTICAL_LINE = "|   "
INDENT = "    "

# Ignorieren
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
    "collages",
    "release",
    ".idea",
    ".ruff_cache",
    "htmlcov",
    "__pycache__",
    "__main__",
    "site",
}
IGNORE_EXTENSIONS = {".pyc"}


def should_ignore(path):
    name = os.path.basename(path)
    if name in IGNORE_DIRS:
        return True
    if os.path.isfile(path):
        ext = os.path.splitext(path)[1]
        return ext in IGNORE_EXTENSIONS
    return False

def normalize_type(type_str: str | None) -> str | None:
    if not type_str:
        return None

    type_str = type_str.replace("typing.", "")

    if type_str.startswith("Optional["):
        inner = type_str[len("Optional["):-1]
        return f"{inner} | None"

    if type_str.startswith("Union["):
        inner = type_str[len("Union["):-1]
        return inner.replace(", ", " | ")

    return type_str

def visibility(name: str) -> int:
    if name.startswith("__") and not name.endswith("__"):
        return 2  # private
    if name.startswith("_"):
        return 1  # protected
    return 0      # public

def format_function_signature(func_node):
    """Erzeugt die Signatur einer Funktion als String"""
    args = []
    for arg in func_node.args.args:
        arg_str = arg.arg
        if arg.annotation:
            arg_str += f": {ast.unparse(arg.annotation)}"
        args.append(arg_str)
    if func_node.args.vararg:
        args.append(f"*{func_node.args.vararg.arg}")
    if func_node.args.kwarg:
        args.append(f"**{func_node.args.kwarg.arg}")
    args_str = ", ".join(args)
    ret = ""
    if func_node.returns:
        ret = f" -> {ast.unparse(func_node.returns)}"
    return f"{func_node.name}({args_str}){ret}"


def parse_python_file(file_path: str):
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            node = ast.parse(f.read(), filename=file_path)
    except Exception:
        return []

    structure = []
    for child in node.body:
        if isinstance(child, ast.ClassDef):
            class_entry = {
                "type": "class",
                "name": child.name,
                "class_attributes": [],  # Klassenvariablen
                "instance_attributes": [],  # self.*
                "methods": [],
            }

            for item in child.body:
                if isinstance(item, ast.FunctionDef):
                    sig = format_function_signature(item)
                    class_entry["methods"].append(sig)

                elif isinstance(item, ast.Assign):
                    for target in item.targets:
                        if isinstance(target, ast.Name):
                            class_entry["class_attributes"].append(
                                (target.id, None)
                            )

                elif isinstance(item, ast.AnnAssign):
                    if isinstance(item.target, ast.Name):
                        type_str = ast.unparse(item.annotation) if item.annotation else None
                        class_entry["class_attributes"].append(
                            (item.target.id, type_str)
                        )

                # Instanzattribute aus Methoden
                if isinstance(item, ast.FunctionDef):
                    for stmt in ast.walk(item):
                        if isinstance(stmt, ast.AnnAssign):
                            target = stmt.target
                            if (
                                    isinstance(target, ast.Attribute)
                                    and isinstance(target.value, ast.Name)
                                    and target.value.id == "self"
                            ):
                                type_str = ast.unparse(stmt.annotation) if stmt.annotation else None
                                class_entry["instance_attributes"].append(
                                    (target.attr, type_str)
                                )

                        elif isinstance(stmt, ast.Assign):
                            for target in stmt.targets:
                                if (
                                        isinstance(target, ast.Attribute)
                                        and isinstance(target.value, ast.Name)
                                        and target.value.id == "self"
                                ):
                                    class_entry["instance_attributes"].append(
                                        (target.attr, None)
                                    )
            # remove duplicates
            class_entry["instance_attributes"] = list(dict.fromkeys(class_entry["instance_attributes"]))
            structure.append(class_entry)

        elif isinstance(child, ast.FunctionDef):
            sig = format_function_signature(child)
            structure.append({"type": "function", "signature": sig})

    return structure


def show_tree(
    path: str,
    prefix: str = "",
    show_code: bool = False,
    output: str = "tree",
    md_lines: list[str] | None = None,
    json_data: list | None = None,
):
    try:
        items = sorted(os.listdir(path))
    except PermissionError:
        return

    items = [i for i in items if not should_ignore(os.path.join(path, i))]

    for index, item in enumerate(items):
        full_path = os.path.join(path, item)
        is_last = index == len(items) - 1
        connector = LAST_BRANCH if is_last else BRANCH
        symbol = FOLDER_SYMBOL if os.path.isdir(full_path) else FILE_SYMBOL

        if output == "tree":
            print(f"{prefix}{connector}{symbol} {item}")
        elif output == "md":
            md_lines.append(f"{'  ' * prefix.count(INDENT)}- **{item}**")
        elif output == "json":
            json_data.append({"type": "dir" if os.path.isdir(full_path) else "file", "name": item})

        next_prefix = prefix + (INDENT if is_last else VERTICAL_LINE)

        if os.path.isdir(full_path):
            show_tree(
                full_path,
                next_prefix,
                show_code,
                output,
                md_lines,
                json_data,
            )

        elif show_code and item.endswith(".py"):
            code_structure = parse_python_file(full_path)

            for entry in code_structure:
                if entry["type"] != "class":
                    continue

                # Dataclass erkennen
                is_dataclass = any(
                    isinstance(dec, ast.Name) and dec.id == "dataclass"
                    or isinstance(dec, ast.Attribute) and dec.attr == "dataclass"
                    for dec in entry.get("decorators", [])
                )

                class_header = f"{CLASS_SYMBOL} {entry['name']}"
                if is_dataclass:
                    class_header += " @dataclass"

                if output == "tree":
                    print(f"{next_prefix}{BRANCH}{class_header}")
                elif output == "md":
                    md_lines.append(f"### Class `{entry['name']}`{' (dataclass)' if is_dataclass else ''}")
                elif output == "json":
                    json_data.append({
                        "type": "class",
                        "name": entry["name"],
                        "dataclass": is_dataclass,
                        "attributes": [],
                        "methods": [],
                    })

                attr_prefix = next_prefix + VERTICAL_LINE

                # Attribute sammeln & sortieren
                attrs = []

                for name, typ in entry["class_attributes"]:
                    attrs.append((name, normalize_type(typ), "class"))

                for name, typ in entry["instance_attributes"]:
                    attrs.append((f"self.{name}", normalize_type(typ), "instance"))

                attrs.sort(key=lambda x: (visibility(x[0]), x[0]))

                for name, typ, _ in attrs:
                    type_str = f": {typ}" if typ else ""
                    if output == "tree":
                        print(f"{attr_prefix}{BRANCH}{ATTR_SYMBOL} {name}{type_str}")
                    elif output == "md":
                        md_lines.append(f"- `{name}{type_str}`")
                    elif output == "json":
                        json_data[-1]["attributes"].append(
                            {"name": name, "type": typ}
                        )

                # Methoden
                methods = sorted(entry["methods"], key=lambda m: (visibility(m), m))

                for method in methods:
                    if output == "tree":
                        print(f"{attr_prefix}{BRANCH}{FUNC_SYMBOL} {entry['name']}.{method}")
                    elif output == "md":
                        md_lines.append(f"- `{method}`")
                    elif output == "json":
                        json_data[-1]["methods"].append(method)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Shows directory and Python code structure as a tree."
    )
    parser.add_argument("path", nargs="?", default=".", help="Start directory")
    parser.add_argument(
        "--show-code",
        action="store_true",
        default=False,
        help="Shows functions, classes and attributes in .py files",
    )
    parser.add_argument("--md", action="store_true", help="Output as Markdown")
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    if args.md:
        md_lines = []
        show_tree(args.path, show_code=args.show_code, output="md", md_lines=md_lines)
        print("\n".join(md_lines))

    elif args.json:
        json_data = []
        show_tree(args.path, show_code=args.show_code, output="json", json_data=json_data)
        import json

        print(json.dumps(json_data, indent=2))

    else:
        show_tree(args.path, show_code=args.show_code)

    print('\nSymbol description:')
    print(f"{FOLDER_SYMBOL} - Directory")
    print(f"{FILE_SYMBOL} - File")
    print(f"{CLASS_SYMBOL} - Class")
    print(f"{FUNC_SYMBOL} - Function/Method")
    print(f"{ATTR_SYMBOL} - Attribute")
    print(args)
