from pathlib import Path

class TreePath(Path):
    _flavour = Path('src/mktree')._flavour

    def __new__(cls, *args, **kwargs):
        """
        If first argument looks like a multiline tree spec,
        treat it as such and route through from_tree.
        Otherwise behave like a normal Path.
        """
        # Called before __init__ — ONLY detect & redirect here
        if args and isinstance(args[0], str) and "\n" in args[0]:
            # "args[0]" is tree text; ignore other args
            return cls.from_tree(args[0])

        # Default behavior → treat as regular path construction
        self = super().__new__(cls, *args, **kwargs)

        # attach fields
        self.children: list["TreePath"] = []
        self.comment: str = ""
        self.is_dir_spec: bool = False
        return self


    def add_child(self, child: "TreePath"):
        self.children.append(child)
        return child

    def __repr__(self):
        return f"TreePath({super().__str__()!r}, is_dir={self.is_dir_spec}, children={len(self.children)})"

    def reparent(self, new_parent: "TreePath") -> "TreePath":
        return self.rebase(new_parent / self.name)

    def rebase(self, new_root_path: Path) -> "TreePath":
        new_root = type(self)(new_root_path)
        new_root.is_dir_spec = self.is_dir_spec
        new_root.comment = self.comment
        new_root.children = []
        for c in self.children:
            new_root.add_child(c.reparent(new_root))
        return new_root

    def mktree(self, mode=0o777, parents=True, exist_ok=True):
        """
        Ensure that this Path exists in the filesystem.

        Behavior:
        - If this path ends with a directory, create it recursively.
        - If this path is a file (does not exist yet), ensure parent exists,
          then create the file empty (touch).
        """
        if self.is_dir_spec:
            if not self.exists():
                # ambiguous: could be dir or file — default: treat as directory
                self.mkdir(mode=mode, parents=parents, exist_ok=exist_ok)
            for child in self.children:
                child.mktree(mode, parents=False, exist_ok=exist_ok)
        else:
            # If suffix is non-empty → definitely a file path
            if not self.exists():
                self.parent.mkdir(mode=mode, parents=parents, exist_ok=True)
            self.write_comment()
        return self

    def write_comment(self):
        if not self.exists():
            self.touch()
        with self.open("r") as f:
            st = f.read(4)
        sfx = self.suffix
        if sfx == ".py" and not st.startswith('"""'):
            s = self.read_text()
            self.write_text(f'"""{self.comment}"""\n' + s)
            return
        elif sfx in [".js", ".ts"] and not st.startswith("//"):
            s = self.read_text()
            self.write_text(f'// {self.comment}\n' + s)
            return
        elif sfx == ".md" and not st.strip():
            self.write_text(self.comment)
            return
        elif sfx == ".sh" and not st.startswith("# "):
            s = self.read_text()
            self.write_text(f'# {self.comment}\n' + s)
            return


    @classmethod
    def from_tree(
            cls,
            tree_text: str,
            root_path: str | Path = None,
            parent_path: str | Path = None,
            indent_size: int = 2,
    ) -> "TreePath":

        if root_path is not None:
            root_path = Path(root_path).expanduser()

        if parent_path is not None:
            parent_path = Path(parent_path).expanduser()

        # normalize tabs
        tree_text = tree_text.replace("\t", " " * indent_size)

        lines = [l.rstrip() for l in tree_text.splitlines() if l.strip()]
        raw_roots: list[TreePath] = []
        stack: list[TreePath] = []

        # First pass: parse tree into raw roots
        for line in lines:
            leading = len(line) - len(line.lstrip(" "))
            level = leading // indent_size
            content = line.lstrip(" ")

            if '#' in content:
                name_part, comment = content.split("#", 1)
                comment = comment.strip()
            else:
                name_part, comment = content, ""

            name_part = name_part.rstrip()
            if not name_part:
                continue

            is_dir = name_part.endswith("/")
            name = name_part[:-1] if is_dir else name_part

            if level == 0:
                parent = None
            else:
                stack = stack[:level]
                parent = stack[level - 1]

            node = cls(name) if parent is None else cls(parent, name)
            node.comment = comment
            node.is_dir_spec = is_dir

            if parent is None:
                raw_roots.append(node)
            else:
                parent.add_child(node)

            if is_dir:
                if level == len(stack):
                    stack.append(node)
                else:
                    stack[level] = node

        # === Core selection logic ===

        if len(raw_roots) == 1:
            base_root = raw_roots[0]

            # Parent wrapping always wins
            if parent_path is not None:
                parent = cls(parent_path)
                parent.is_dir_spec = True
                parent.comment = ""
                parent.children = [base_root.reparent(parent)]
                return parent

            # Otherwise root relabeling
            if root_path is not None:
                return base_root.rebase(root_path)

            # Otherwise just return that single root
            return base_root

        # multiple roots case always means artificial top
        if parent_path is not None:
            top = cls(parent_path)
        else:
            top = cls(root_path or ".")  # root_path here means "take that name/path"

        top.is_dir_spec = True
        top.comment = ""
        top.children = [r.reparent(top) for r in raw_roots]
        return top



# Example usage
if __name__ == "__main__":
    t = TreePath.from_tree("""\
your_project/
  corpora/
    __init__.py
    base.py              # ABCs
    wikipedia.py
    stackoverflow.py
    reddit.py
    generic_web.py
  pipeline/
    __init__.py
    unigrams.py          # pass 1
    ngrams.py            # pass 2
    build_index.py       # builds your prefix/completion trees
  config/
    corpora.yaml         # what corpora, where, params
  scripts/
    build_unigrams.py
    build_ngrams.py
    build_completions.py
""", "test")

