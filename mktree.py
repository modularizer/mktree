#!/usr/bin/env python3

import argparse
import json
import sys
from pathlib import Path

class TreePath(Path):
    _flavour = Path()._flavour

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

    def fully_exists(self):
        return self.exists() and all(child.fully_exists() for child in self.children)

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
    def _detect_format(cls, tree_text: str) -> str:
        """
        Detect the format of the tree specification.
        
        Returns:
            'json', 'yaml', 'git', 'ascii_box', 'unicode_box', 'prefix', or 'indent'
        """
        stripped = tree_text.strip()
        
        # Check for JSON
        if stripped.startswith('{') or stripped.startswith('['):
            try:
                json.loads(stripped)
                return 'json'
            except (json.JSONDecodeError, ValueError):
                pass
        
        # Check for YAML (simple heuristic - starts with key: or -)
        if any(line.strip().startswith(('---', 'key:', '- ')) for line in stripped.splitlines()[:3]):
            return 'yaml'
        
        lines = [l.rstrip() for l in stripped.splitlines() if l.strip()]
        if not lines:
            return 'indent'
        
        # Check for Git ls-tree format (starts with mode and type)
        first_line = lines[0].strip()
        if first_line and (first_line.startswith(('040000', '100644', '100755', '120000', '160000')) or 
                          ' tree ' in first_line or ' blob ' in first_line):
            return 'git'
        
        # Check for ASCII box-drawing
        if any('+--' in line or '\\--' in line or (line.strip().startswith('|') and '--' in line) for line in lines):
            return 'ascii_box'
        
        # Check for Unicode box-drawing
        if any('├' in line or '└' in line or '│' in line for line in lines):
            return 'unicode_box'
        
        # Check for prefix markers (+ or - at start)
        if any(line.strip().startswith(('+ ', '- ')) for line in lines):
            return 'prefix'
        
        # Default to indentation-based
        return 'indent'
    
    @classmethod
    def _parse_ascii_box_line(cls, line: str) -> tuple[int, str] | None:
        """
        Parse a line with ASCII box-drawing characters (+--, |, \--).
        
        Examples:
            +-- item          -> level 0
            |   +-- item      -> level 1
            |   \-- item      -> level 1
            \-- item          -> level 0
                \-- item      -> level 1 (4 spaces before \--)
        
        Returns:
            (level, content) tuple if line uses ASCII box-drawing format, None otherwise.
        """
        if '+--' not in line and '\\--' not in line and not (line.strip().startswith('|') and '--' in line):
            return None
        
        # Find where +-- or \-- appears
        branch_marker = None
        branch_pos = -1
        
        if '+-- ' in line:
            branch_pos = line.find('+-- ')
            branch_marker = '+-- '
        elif '\\-- ' in line:
            branch_pos = line.find('\\-- ')
            branch_marker = '\\-- '
        
        if branch_pos == -1:
            return None
        
        # Count | characters before the branch marker
        level = 0
        prefix = line[:branch_pos]
        
        # Count | characters in the prefix
        i = 0
        while i < len(prefix):
            if prefix[i] == '|':
                level += 1
                # Skip | and following spaces
                i += 1
                while i < len(prefix) and prefix[i] == ' ':
                    i += 1
            elif prefix[i] == ' ':
                i += 1
            else:
                i += 1
        
        # Handle leading spaces before box-drawing chars
        leading_spaces = len(line) - len(line.lstrip(" "))
        if leading_spaces > 0 and not prefix.lstrip().startswith('|'):
            level += leading_spaces // 4
        
        # Extract content after +-- or \--
        content = line[branch_pos + len(branch_marker):].strip()
        
        return (level, content)
    
    @classmethod
    def _parse_prefix_line(cls, line: str) -> tuple[int, str, bool] | None:
        """
        Parse a line with prefix markers (+ for directories, - for files).
        
        Examples:
            + dir/            -> level 0, directory
            + subdir/         -> level 0, directory
              - file.txt      -> level 1, file
              - another.txt   -> level 1, file
            - root.txt        -> level 0, file
        
        Returns:
            (level, content, is_dir) tuple if line uses prefix format, None otherwise.
        """
        stripped = line.lstrip()
        if not stripped.startswith(('+ ', '- ')):
            return None
        
        # Determine if directory or file
        is_dir = stripped.startswith('+ ')
        marker_len = 2  # "+ " or "- "
        
        # Count leading spaces to determine level
        leading_spaces = len(line) - len(stripped)
        level = leading_spaces // 2  # Typically 2 spaces per level
        
        # Extract content after marker
        content = stripped[marker_len:].strip()
        
        return (level, content, is_dir)
    
    @classmethod
    def _parse_git_line(cls, line: str) -> tuple[str, bool] | None:
        """
        Parse a line in Git ls-tree format.
        
        Examples:
            040000 tree dir/
            100644 blob file.txt
        
        Returns:
            (name, is_dir) tuple if line is in git format, None otherwise.
        """
        parts = line.strip().split()
        if len(parts) < 3:
            return None
        
        mode = parts[0]
        obj_type = parts[1]
        name = ' '.join(parts[2:])  # Handle names with spaces
        
        # Determine if directory
        is_dir = (mode.startswith('040') and obj_type == 'tree') or name.endswith('/')
        
        return (name.rstrip('/'), is_dir)
    
    @classmethod
    def _parse_json_tree(cls, tree_data: dict | list, parent_node: "TreePath" = None) -> list["TreePath"]:
        """
        Parse a JSON tree structure into TreePath nodes.
        
        Examples:
            {"dir/": {"file.txt": null}}
            [{"dir/": {"file.txt": null}}]
        """
        roots = []
        
        if isinstance(tree_data, list):
            # List of root items
            for item in tree_data:
                roots.extend(cls._parse_json_tree(item, parent_node))
        elif isinstance(tree_data, dict):
            # Dictionary where keys are names and values are children
            for name, children in tree_data.items():
                is_dir = name.endswith('/') or (isinstance(children, (dict, list)) and children)
                name_clean = name.rstrip('/')
                
                if parent_node:
                    node = cls(parent_node, name_clean)
                else:
                    node = cls(name_clean)
                
                node.is_dir_spec = is_dir
                
                if is_dir and children:
                    if isinstance(children, (dict, list)):
                        child_nodes = cls._parse_json_tree(children, node)
                        for child_node in child_nodes:
                            node.add_child(child_node)
                    elif children is not None:
                        # Non-null value means it's a file with content (we'll ignore content for now)
                        node.is_dir_spec = False
                
                if parent_node:
                    roots.append(node)
                else:
                    roots.append(node)
        
        return roots
    
    @classmethod
    def _parse_box_drawing_line(cls, line: str) -> tuple[int, str] | None:
        """
        Parse a line with box-drawing characters (├──, └──, │).
        
        Examples:
            ├── item          -> level 0
            │   ├── item      -> level 1
            │   └── item      -> level 1
            └── item          -> level 0
                └── item      -> level 1 (4 spaces before └──)
        
        Returns:
            (level, content) tuple if line uses box-drawing format, None otherwise.
            Level is 0-based (0 = root level).
        """
        # Check if line contains box-drawing characters
        if '├' not in line and '└' not in line and '│' not in line:
            return None
        
        # Find where ├── or └── appears in the original line
        branch_marker = None
        branch_pos = -1
        
        if '├── ' in line:
            branch_pos = line.find('├── ')
            branch_marker = '├── '
        elif '└── ' in line:
            branch_pos = line.find('└── ')
            branch_marker = '└── '
        
        if branch_pos == -1:
            return None
        
        # Count │ characters before the branch marker
        # Each │ indicates one level of nesting
        level = 0
        prefix = line[:branch_pos]
        
        # Count │ characters in the prefix
        i = 0
        while i < len(prefix):
            if prefix[i] == '│':
                level += 1
                # Skip │ and following spaces (usually 3-4 spaces)
                i += 1
                while i < len(prefix) and prefix[i] == ' ':
                    i += 1
            elif prefix[i] == ' ':
                # Regular spaces - if we haven't seen any │ yet, these might indicate nesting
                # But typically, spaces before │ are part of the │   pattern
                # Spaces after │ are just formatting
                i += 1
            else:
                # Unexpected character
                i += 1
        
        # Handle case where there are leading spaces before any box-drawing chars
        # Like "    └── item" (4 spaces) - this is level 1, child of previous root
        leading_spaces = len(line) - len(line.lstrip(" "))
        if leading_spaces > 0 and not prefix.lstrip().startswith('│'):
            # There are leading spaces but no │ - this indicates nesting
            # Typically 4 spaces = 1 level of nesting
            level += leading_spaces // 4
        
        # Extract content after ├── or └──
        content = line[branch_pos + len(branch_marker):].strip()
        
        return (level, content)
    
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

        # Detect format
        format_type = cls._detect_format(tree_text)
        
        # Handle JSON format
        if format_type == 'json':
            try:
                tree_data = json.loads(tree_text.strip())
                raw_roots = cls._parse_json_tree(tree_data)
                # Skip to core selection logic
                if len(raw_roots) == 1:
                    base_root = raw_roots[0]
                    if parent_path is not None:
                        parent = cls(parent_path)
                        parent.is_dir_spec = True
                        parent.comment = ""
                        parent.children = [base_root.reparent(parent)]
                        return parent
                    if root_path is not None:
                        return base_root.rebase(root_path)
                    return base_root
                # Multiple roots
                if parent_path is not None:
                    top = cls(parent_path)
                else:
                    top = cls(root_path or ".")
                top.is_dir_spec = True
                top.comment = ""
                top.children = [r.reparent(top) for r in raw_roots]
                return top
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON format: {e}")
        
        # Handle YAML format (basic support - could be enhanced with PyYAML)
        if format_type == 'yaml':
            # For now, treat YAML-like structures as indentation-based
            # Full YAML support would require PyYAML dependency
            format_type = 'indent'
        
        # Normalize tabs for text-based formats
        tree_text = tree_text.replace("\t", " " * indent_size)
        lines = [l.rstrip() for l in tree_text.splitlines() if l.strip()]
        if not lines:
            raise ValueError("Tree specification cannot be empty")
        
        raw_roots: list[TreePath] = []
        stack: list[TreePath] = []

        # First pass: parse tree into raw roots
        for line in lines:
            level = 0
            content = ""
            is_dir = False
            comment = ""
            
            if format_type == 'git':
                # Git ls-tree format - parse and build hierarchy from paths
                parsed = cls._parse_git_line(line)
                if parsed is None:
                    continue
                name, is_dir = parsed
                # Git format uses paths like "dir/subdir/file.txt"
                # We need to split by / and build the hierarchy
                parts = name.split('/')
                current_parent = None
                for i, part in enumerate(parts):
                    is_part_dir = is_dir if i == len(parts) - 1 else True
                    if current_parent is None:
                        # Root level
                        # Check if this root already exists
                        existing = next((r for r in raw_roots if r.name == part), None)
                        if existing:
                            current_parent = existing
                        else:
                            node = cls(part)
                            node.is_dir_spec = is_part_dir
                            raw_roots.append(node)
                            current_parent = node
                    else:
                        # Check if child already exists
                        existing = next((c for c in current_parent.children if c.name == part), None)
                        if existing:
                            current_parent = existing
                        else:
                            node = cls(current_parent, part)
                            node.is_dir_spec = is_part_dir
                            current_parent.add_child(node)
                            current_parent = node
                continue  # Skip the normal processing for Git format
            elif format_type == 'unicode_box':
                # Unicode box-drawing format
                parsed = cls._parse_box_drawing_line(line)
                if parsed is None:
                    continue
                level, content = parsed
            elif format_type == 'ascii_box':
                # ASCII box-drawing format
                parsed = cls._parse_ascii_box_line(line)
                if parsed is None:
                    continue
                level, content = parsed
            elif format_type == 'prefix':
                # Prefix marker format
                parsed = cls._parse_prefix_line(line)
                if parsed is None:
                    continue
                level, content, is_dir = parsed
            else:
                # Standard indentation format
                leading = len(line) - len(line.lstrip(" "))
                level = leading // indent_size
                content = line.lstrip(" ")

            # Extract comment if present
            if '#' in content:
                name_part, comment = content.split("#", 1)
                comment = comment.strip()
            else:
                name_part, comment = content, ""

            name_part = name_part.rstrip()
            if not name_part:
                continue

            # Determine if directory (unless already determined by format)
            if format_type != 'prefix' and format_type != 'git':
                is_dir = name_part.endswith("/")
                name = name_part[:-1] if is_dir else name_part
            else:
                name = name_part.rstrip("/")
                # Ensure trailing / is removed if present
                if name != name_part:
                    is_dir = True

            if level == 0:
                parent = None
            else:
                stack = stack[:level]
                parent = stack[level - 1] if stack else None

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



def main():
    parser = argparse.ArgumentParser(
        description="Create directory trees from a tree specification"
    )
    parser.add_argument(
        "tree",
        nargs="?",
        help="Optional tree specification. If not provided, will prompt for multiline input."
    )
    parser.add_argument(
        "--root-path",
        type=str,
        help="Root path for the tree"
    )
    parser.add_argument(
        "--parent-path",
        type=str,
        help="Parent path to wrap the tree"
    )
    parser.add_argument(
        "--indent-size",
        type=int,
        default=2,
        help="Indent size for parsing the tree (default: 2)"
    )
    parser.add_argument(
        "--mode",
        type=lambda x: int(x, 8),
        default=0o777,
        help="File mode in octal (default: 777)"
    )
    parser.add_argument(
        "--no-parents",
        action="store_false",
        dest="parents",
        help="Don't create parent directories"
    )
    parser.add_argument(
        "--no-exist-ok",
        action="store_false",
        dest="exist_ok",
        help="Don't ignore existing directories"
    )
    parser.add_argument(
        "-y", "--yes",
        action="store_true",
        help="Automatically use default path without prompting"
    )
    
    args = parser.parse_args()
    
    # Get tree text - either from argument or prompt for input
    if args.tree:
        tree_text = args.tree
    else:
        print("Enter tree specification (end with Ctrl+D or empty line):", file=sys.stderr)
        lines = []
        try:
            while True:
                line = input()
                if not line:
                    break
                lines.append(line)
        except EOFError:
            pass
        tree_text = "\n".join(lines)
    
    if not tree_text.strip():
        parser.error("Tree specification cannot be empty")
    
    # Determine default path from tree structure
    # Parse tree to find the first root name for default
    lines = [l.rstrip() for l in tree_text.splitlines() if l.strip()]
    default_path = "./demo"
    if lines:
        first_line = lines[0].lstrip()
        if '#' in first_line:
            first_line = first_line.split("#", 1)[0]
        first_line = first_line.rstrip()
        if first_line.endswith("/"):
            first_line = first_line[:-1]
        if first_line:
            default_path = f"./{first_line}"
    
    # Prompt for path if neither root_path nor parent_path is specified
    if args.root_path is None and args.parent_path is None:
        # Prompt user for path
        default = Path(default_path).expanduser().resolve()
        default_str = str(default)
        
        if not args.yes:
            # Prompt the user
            prompt = f"Make at path: [{default_str}]"
            print(prompt, end=" ", file=sys.stderr)
            sys.stderr.flush()
            
            try:
                user_input = input("").strip()
            except (EOFError, KeyboardInterrupt):
                # User cancelled, use default
                print(file=sys.stderr)
                user_input = ""
            
            if user_input:
                # User provided a path, use it as parent_path
                args.parent_path = user_input
            else:
                # User just hit enter, use default
                args.parent_path = default_str
        else:
            # Auto-yes: use default
            args.parent_path = default_str
    
    # Build kwargs for from_tree
    from_tree_kwargs = {}
    if args.root_path is not None:
        from_tree_kwargs["root_path"] = args.root_path
    if args.parent_path is not None:
        from_tree_kwargs["parent_path"] = args.parent_path
    if args.indent_size is not None:
        from_tree_kwargs["indent_size"] = args.indent_size
    
    # Build kwargs for mktree
    mktree_kwargs = {
        "mode": args.mode,
        "parents": args.parents,
        "exist_ok": args.exist_ok,
    }
    
    # Create tree and execute
    tree_path = TreePath.from_tree(tree_text, **from_tree_kwargs)
    tree_path.mktree(**mktree_kwargs)
    print(f"Created tree at: {tree_path}")


if __name__ == "__main__":
    main()

