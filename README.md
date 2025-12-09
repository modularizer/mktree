# mktree

Create directory trees from a simple text specification. Quickly scaffold project structures, create nested directories, and generate files with comments—all from a single tree description.


## Installation
```bash
git clone <repository-url>
cd mktree
pip install -e .
```

## Quick Start
Just run
```bash
mktree
```

You'll be prompted to enter your tree specification. End with Ctrl+D or an empty line.

## Command-Line Options
- `--root-path PATH`: Set the root path for the tree (relabels the root)
- `--parent-path PATH`: Wrap the tree in a parent directory
- `-y, --yes`: Automatically use default path without prompting
- `--indent-size N`: Set indentation size (default: 2)
- `--mode MODE`: Set file permissions in octal (default: 777)
- `--no-parents`: Don't create parent directories
- `--no-exist-ok`: Don't ignore existing directories
- **NOTE**: If neither `--root-path` nor `--parent-path` is specified, `mktree` will prompt you for where to create the folder, showing a default based on the first root in your tree, unless you specify `-y`

### From Command Line

```bash
mktree "my_project/
  src/
    __init__.py
  tests/
    test_main.py"
```

### From File

```bash
mktree < tree.txt
```

## Tree Specification Format

The tree specification supports multiple formats. mktree automatically detects the format based on the input:

### Format 1: Indentation-Based (Default)
```
my_project/
  src/
    __init__.py
    main.py              # This comment will be written as a docstring at the top of main.py
  tests/
    __init__.py
    test_main.py         # Unit tests
  README.md              # Project documentation
  setup.py
```

### Format 2: Unicode Box-Drawing Characters
```
├── my_project/
│   ├── src/
│   │   ├── __init__.py
│   │   └── main.py              # This comment will be written as a docstring at the top of main.py
│   └── tests/
│       ├── __init__.py
│       └── test_main.py         # Unit tests
├── README.md                     # Project documentation
└── setup.py
```

### Format 3: ASCII Box-Drawing Characters
```
+-- my_project/
|   +-- src/
|   |   +-- __init__.py
|   |   \-- main.py
|   \-- tests/
|       \-- test_main.py
\-- README.md
```

### Format 4: Prefix Markers
```
+ my_project/
+ src/
  - __init__.py
  - main.py              # Main entry point
+ tests/
  - __init__.py
  - test_main.py         # Unit tests
- README.md              # Project documentation
- setup.py
```

### Format 5: JSON
```json
{
  "my_project/": {
    "src/": {
      "__init__.py": null,
      "main.py": null
    },
    "tests/": {
      "__init__.py": null,
      "test_main.py": null
    },
    "README.md": null,
    "setup.py": null
  }
}
```

### Format 6: Git ls-tree Format
Git tree format (like `git ls-tree -r --name-only`):
```
040000 tree my_project/
040000 tree my_project/src/
100644 blob my_project/src/__init__.py
100644 blob my_project/src/main.py
040000 tree my_project/tests/
100644 blob my_project/tests/__init__.py
100644 blob my_project/tests/test_main.py
100644 blob my_project/README.md
100644 blob my_project/setup.py
```

**Note:** mktree automatically detects the format based on the input. You can mix formats in different files, but each individual input should use a single format.

This creates:
```
my_project/
├── src/
│   ├── __init__.py
│   └── main.py
├── tests/
│   ├── __init__.py
│   └── test_main.py
├── README.md
└── setup.py
```



## Examples

### Example 1: Simple Project Structure

```bash
mktree "project/
  src/
    __init__.py
    app.py
  tests/
    test_app.py
  README.md"
```


## Interactive Mode

Run without arguments to enter interactive mode:

```bash
$ mktree
Enter tree specification (end with Ctrl+D or empty line):
my_project/
  src/
    main.py
  tests/
    test_main.py
^D
Make at path: [./my_project] 
Created tree at: ./my_project
```

## Requirements

- Python 3.8 or higher
- No external dependencies

## License

Unlicense (Public Domain)

## Contributing

Contributions welcome! Please feel free to submit issues or pull requests.

