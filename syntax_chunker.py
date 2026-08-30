"""
syntax_chunker.py - Multi-language syntax-aware AST and structure code chunker for RAG.
Supports Python, JavaScript, TypeScript, Go, Rust, Java, C#, C++, and Markdown.
"""

from __future__ import annotations

import ast
import hashlib
import re
from pathlib import Path
from typing import Any, NamedTuple


class CodeChunk(NamedTuple):
    id: str
    file_path: str
    symbol_name: str | None
    symbol_type: str
    start_line: int
    end_line: int
    content: str
    docstring: str | None
    embedding: list[float]
    last_modified: float
    content_hash: str


class SyntaxChunker:
    """Multi-language syntax-aware chunker that extracts classes, functions,

    interfaces, structs, and methods with accurate line boundaries.
    """

    def chunk(self, file_path: str, content: str, modified: float) -> list[CodeChunk]:
        ext = Path(file_path).suffix.lower()

        if ext == ".py":
            try:
                chunks = self.chunk_python(file_path, content, modified)
                if chunks:
                    return chunks
            except Exception:
                pass

        elif ext in {".js", ".jsx", ".mjs", ".ts", ".tsx"}:
            try:
                chunks = self.chunk_javascript_typescript(file_path, content, modified)
                if chunks:
                    return chunks
            except Exception:
                pass

        elif ext == ".go":
            try:
                chunks = self.chunk_go(file_path, content, modified)
                if chunks:
                    return chunks
            except Exception:
                pass

        elif ext == ".rs":
            try:
                chunks = self.chunk_rust(file_path, content, modified)
                if chunks:
                    return chunks
            except Exception:
                pass

        elif ext in {".java", ".cs", ".cpp", ".c", ".h", ".hpp"}:
            try:
                chunks = self.chunk_c_like(file_path, content, modified)
                if chunks:
                    return chunks
            except Exception:
                pass

        elif ext in {".md", ".markdown"}:
            try:
                chunks = self.chunk_markdown(file_path, content, modified)
                if chunks:
                    return chunks
            except Exception:
                pass

        return self.chunk_generic(file_path, content, modified)

    # ══════════════════════════════════════════════════════════════════════════
    # ── Python Syntax Chunker (AST)
    # ══════════════════════════════════════════════════════════════════════════

    def chunk_python(self, file_path: str, content: str, modified: float) -> list[CodeChunk]:
        tree = ast.parse(content)
        lines = content.splitlines()
        chunks: list[CodeChunk] = []

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                start = int(node.lineno)
                end = int(getattr(node, "end_lineno", node.lineno) or node.lineno)
                value = "\n".join(lines[start - 1 : end])
                symbol_type = "class" if isinstance(node, ast.ClassDef) else "function"
                chunks.append(
                    self._make(
                        file_path,
                        node.name,
                        symbol_type,
                        start,
                        end,
                        value,
                        ast.get_docstring(node),
                        modified,
                    )
                )

        module_lines = []
        for index, line in enumerate(lines[:300], 1):
            if line.startswith(("import ", "from ", "__", "#")) or not line.strip():
                module_lines.append((index, line))
        if module_lines:
            chunks.insert(
                0,
                self._make(
                    file_path,
                    Path(file_path).stem,
                    "module",
                    module_lines[0][0],
                    module_lines[-1][0],
                    "\n".join(line for _, line in module_lines),
                    ast.get_docstring(tree),
                    modified,
                ),
            )

        return chunks or self.chunk_generic(file_path, content, modified)

    # ══════════════════════════════════════════════════════════════════════════
    # ── JavaScript / TypeScript Syntax Chunker
    # ══════════════════════════════════════════════════════════════════════════

    def chunk_javascript_typescript(self, file_path: str, content: str, modified: float) -> list[CodeChunk]:
        lines = content.splitlines()
        chunks: list[CodeChunk] = []

        # Patterns for JS/TS declarations
        patterns = [
            # class Name
            (re.compile(r"^(?:export\s+(?:default\s+)?)?class\s+([A-Za-z0-9_$]+)"), "class"),
            # interface Name
            (re.compile(r"^(?:export\s+)?interface\s+([A-Za-z0-9_$]+)"), "interface"),
            # type Name =
            (re.compile(r"^(?:export\s+)?type\s+([A-Za-z0-9_$]+)\s*="), "type"),
            # enum Name
            (re.compile(r"^(?:export\s+)?enum\s+([A-Za-z0-9_$]+)"), "enum"),
            # function name(...)
            (re.compile(r"^(?:export\s+(?:default\s+)?)?(?:async\s+)?function\s*([A-Za-z0-9_$]+)?\s*\("), "function"),
            # const/let/var name = (async) (...) => / function
            (re.compile(r"^(?:export\s+)?(?:const|let|var)\s+([A-Za-z0-9_$]+)\s*=\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z0-9_$]+)\s*=>"), "function"),
            (re.compile(r"^(?:export\s+)?(?:const|let|var)\s+([A-Za-z0-9_$]+)\s*=\s*(?:async\s*)?function"), "function"),
        ]

        i = 0
        while i < len(lines):
            line = lines[i].strip()
            matched = False
            for pattern, sym_type in patterns:
                m = pattern.search(line)
                if m:
                    name = m.group(1) if m.lastindex and m.group(1) else f"anonymous_{i+1}"
                    start_line = i + 1
                    end_line = self._find_block_end(lines, i)
                    block_content = "\n".join(lines[i : end_line])
                    chunks.append(
                        self._make(
                            file_path,
                            name,
                            sym_type,
                            start_line,
                            end_line,
                            block_content,
                            self._extract_preceding_comment(lines, i),
                            modified,
                        )
                    )
                    i = max(i + 1, end_line)
                    matched = True
                    break
            if not matched:
                i += 1

        return chunks or self.chunk_generic(file_path, content, modified)

    # ══════════════════════════════════════════════════════════════════════════
    # ── Go Syntax Chunker
    # ══════════════════════════════════════════════════════════════════════════

    def chunk_go(self, file_path: str, content: str, modified: float) -> list[CodeChunk]:
        lines = content.splitlines()
        chunks: list[CodeChunk] = []

        func_pattern = re.compile(r"^func\s+(?:\((?:[^)]+)\)\s+)?([A-Za-z0-9_]+)\s*\(")
        struct_pattern = re.compile(r"^type\s+([A-Za-z0-9_]+)\s+struct\b")
        interface_pattern = re.compile(r"^type\s+([A-Za-z0-9_]+)\s+interface\b")

        i = 0
        while i < len(lines):
            line = lines[i].strip()
            sym_name, sym_type = None, None

            fm = func_pattern.search(line)
            if fm:
                sym_name, sym_type = fm.group(1), "function"
            else:
                sm = struct_pattern.search(line)
                if sm:
                    sym_name, sym_type = sm.group(1), "struct"
                else:
                    im = interface_pattern.search(line)
                    if im:
                        sym_name, sym_type = im.group(1), "interface"

            if sym_name and sym_type:
                start_line = i + 1
                end_line = self._find_block_end(lines, i)
                block_content = "\n".join(lines[i : end_line])
                chunks.append(
                    self._make(
                        file_path,
                        sym_name,
                        sym_type,
                        start_line,
                        end_line,
                        block_content,
                        self._extract_preceding_comment(lines, i),
                        modified,
                    )
                )
                i = max(i + 1, end_line)
            else:
                i += 1

        return chunks or self.chunk_generic(file_path, content, modified)

    # ══════════════════════════════════════════════════════════════════════════
    # ── Rust Syntax Chunker
    # ══════════════════════════════════════════════════════════════════════════

    def chunk_rust(self, file_path: str, content: str, modified: float) -> list[CodeChunk]:
        lines = content.splitlines()
        chunks: list[CodeChunk] = []

        patterns = [
            (re.compile(r"^(?:pub(?:\([^)]+\))?\s+)?(?:async\s+)?fn\s+([A-Za-z0-9_]+)"), "function"),
            (re.compile(r"^(?:pub(?:\([^)]+\))?\s+)?struct\s+([A-Za-z0-9_]+)"), "struct"),
            (re.compile(r"^(?:pub(?:\([^)]+\))?\s+)?enum\s+([A-Za-z0-9_]+)"), "enum"),
            (re.compile(r"^(?:pub(?:\([^)]+\))?\s+)?trait\s+([A-Za-z0-9_]+)"), "trait"),
            (re.compile(r"^impl(?:<[^>]+>)?\s+(?:[A-Za-z0-9_]+(?:\s+for\s+)?([A-Za-z0-9_]+)|([A-Za-z0-9_]+))"), "impl"),
        ]

        i = 0
        while i < len(lines):
            line = lines[i].strip()
            matched = False
            for pattern, sym_type in patterns:
                m = pattern.search(line)
                if m:
                    name = m.group(1) or (m.group(2) if len(m.groups()) > 1 else None) or f"block_{i+1}"
                    start_line = i + 1
                    end_line = self._find_block_end(lines, i)
                    block_content = "\n".join(lines[i : end_line])
                    chunks.append(
                        self._make(
                            file_path,
                            name,
                            sym_type,
                            start_line,
                            end_line,
                            block_content,
                            self._extract_preceding_comment(lines, i),
                            modified,
                        )
                    )
                    i = max(i + 1, end_line)
                    matched = True
                    break
            if not matched:
                i += 1

        return chunks or self.chunk_generic(file_path, content, modified)

    # ══════════════════════════════════════════════════════════════════════════
    # ── Java / C# / C++ Syntax Chunker
    # ══════════════════════════════════════════════════════════════════════════

    def chunk_c_like(self, file_path: str, content: str, modified: float) -> list[CodeChunk]:
        lines = content.splitlines()
        chunks: list[CodeChunk] = []

        patterns = [
            (re.compile(r"(?:public|protected|private|static|\s)*class\s+([A-Za-z0-9_]+)"), "class"),
            (re.compile(r"(?:public|protected|private|static|\s)*interface\s+([A-Za-z0-9_]+)"), "interface"),
            (re.compile(r"(?:public|protected|private|static|\s)*struct\s+([A-Za-z0-9_]+)"), "struct"),
            (re.compile(r"(?:public|protected|private|static|async|override|\s)+[A-Za-z0-9_<>\[\]]+\s+([A-Za-z0-9_]+)\s*\([^)]*\)\s*\{?"), "method"),
        ]

        i = 0
        while i < len(lines):
            line = lines[i].strip()
            matched = False
            for pattern, sym_type in patterns:
                m = pattern.search(line)
                if m and not line.endswith(";"):
                    name = m.group(1)
                    start_line = i + 1
                    end_line = self._find_block_end(lines, i)
                    block_content = "\n".join(lines[i : end_line])
                    chunks.append(
                        self._make(
                            file_path,
                            name,
                            sym_type,
                            start_line,
                            end_line,
                            block_content,
                            self._extract_preceding_comment(lines, i),
                            modified,
                        )
                    )
                    i = max(i + 1, end_line)
                    matched = True
                    break
            if not matched:
                i += 1

        return chunks or self.chunk_generic(file_path, content, modified)

    # ══════════════════════════════════════════════════════════════════════════
    # ── Markdown Section Chunker
    # ══════════════════════════════════════════════════════════════════════════

    def chunk_markdown(self, file_path: str, content: str, modified: float) -> list[CodeChunk]:
        lines = content.splitlines()
        chunks: list[CodeChunk] = []
        header_pattern = re.compile(r"^(#{1,4})\s+(.+)$")

        current_header = Path(file_path).stem
        start_line = 1
        current_lines: list[str] = []

        for line_no, line in enumerate(lines, 1):
            m = header_pattern.match(line)
            if m and current_lines:
                text = "\n".join(current_lines).strip()
                if text:
                    chunks.append(
                        self._make(
                            file_path,
                            current_header,
                            "section",
                            start_line,
                            line_no - 1,
                            text,
                            None,
                            modified,
                        )
                    )
                current_header = m.group(2).strip()
                start_line = line_no
                current_lines = [line]
            else:
                current_lines.append(line)

        if current_lines:
            text = "\n".join(current_lines).strip()
            if text:
                chunks.append(
                    self._make(
                        file_path,
                        current_header,
                        "section",
                        start_line,
                        len(lines),
                        text,
                        None,
                        modified,
                    )
                )

        return chunks or self.chunk_generic(file_path, content, modified)

    # ══════════════════════════════════════════════════════════════════════════
    # ── Generic Token / Line Boundary Chunker
    # ══════════════════════════════════════════════════════════════════════════

    def chunk_generic(
        self, file_path: str, content: str, modified: float, max_tokens: int = 300
    ) -> list[CodeChunk]:
        lines = content.splitlines()
        chunks: list[CodeChunk] = []
        current: list[str] = []
        start = 1
        max_chars = max_tokens * 4

        for line_no, line in enumerate(lines, 1):
            boundary = (
                not line.strip()
                and current
                and sum(len(item) + 1 for item in current) >= max_chars // 2
            )
            overflow = (
                current and sum(len(item) + 1 for item in current) + len(line) > max_chars
            )
            if boundary or overflow:
                chunk_text = "\n".join(current).strip()
                if chunk_text:
                    chunks.append(
                        self._make(
                            file_path,
                            None,
                            "doc",
                            start,
                            line_no - 1,
                            chunk_text,
                            None,
                            modified,
                        )
                    )
                current, start = [], line_no + (1 if boundary else 0)
            if line.strip() or current:
                current.append(line)

        if current:
            chunk_text = "\n".join(current).strip()
            if chunk_text:
                chunks.append(
                    self._make(
                        file_path,
                        None,
                        "doc",
                        start,
                        len(lines),
                        chunk_text,
                        None,
                        modified,
                    )
                )

        return [chunk for chunk in chunks if chunk.content]

    # ══════════════════════════════════════════════════════════════════════════
    # ── Helper Methods
    # ══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def _find_block_end(lines: list[str], start_idx: int) -> int:
        """Find the matching closing brace '}' for a block starting at start_idx."""
        brace_count = 0
        found_open = False
        in_string = None
        in_line_comment = False
        in_block_comment = False

        for idx in range(start_idx, len(lines)):
            line = lines[idx]
            j = 0
            while j < len(line):
                ch = line[j]

                # Handle comments
                if not in_string:
                    if not in_block_comment and j + 1 < len(line) and line[j : j + 2] == "//":
                        break
                    if not in_block_comment and j + 1 < len(line) and line[j : j + 2] == "/*":
                        in_block_comment = True
                        j += 2
                        continue
                    if in_block_comment and j + 1 < len(line) and line[j : j + 2] == "*/":
                        in_block_comment = False
                        j += 2
                        continue
                    if in_block_comment:
                        j += 1
                        continue

                # Handle strings
                if ch in ("'", '"', '`') and (j == 0 or line[j - 1] != "\\"):
                    if in_string == ch:
                        in_string = None
                    elif in_string is None:
                        in_string = ch
                    j += 1
                    continue

                if in_string:
                    j += 1
                    continue

                # Count braces
                if ch == "{":
                    brace_count += 1
                    found_open = True
                elif ch == "}":
                    brace_count -= 1
                    if found_open and brace_count == 0:
                        return idx + 1
                j += 1

            if found_open and brace_count == 0:
                return idx + 1

        # Fallback: up to 100 lines or end of file
        return min(start_idx + 60, len(lines))

    @staticmethod
    def _extract_preceding_comment(lines: list[str], start_idx: int) -> str | None:
        """Extract JSDoc / doc comments immediately preceding the definition."""
        comments = []
        idx = start_idx - 1
        while idx >= 0:
            line = lines[idx].strip()
            if line.startswith(("//", "/*", "*", "*/", "#", "///")):
                comments.insert(0, line)
                idx -= 1
            elif not line:
                idx -= 1
            else:
                break
        return "\n".join(comments) if comments else None

    @staticmethod
    def _make(
        file_path: str,
        symbol_name: str | None,
        symbol_type: str,
        start: int,
        end: int,
        content: str,
        docstring: str | None,
        modified: float,
    ) -> CodeChunk:
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        chunk_id = hashlib.sha256(
            f"{file_path}:{start}:{end}:{digest}".encode()
        ).hexdigest()
        return CodeChunk(
            id=chunk_id,
            file_path=file_path,
            symbol_name=symbol_name,
            symbol_type=symbol_type,
            start_line=start,
            end_line=end,
            content=content,
            docstring=docstring,
            embedding=[],
            last_modified=modified,
            content_hash=digest,
        )
