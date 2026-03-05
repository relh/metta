import shutil
import subprocess
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Callable, Iterable, Optional, Sequence

import typer
from pydantic import BaseModel
from rich.progress import Progress, SpinnerColumn, TextColumn

import gitta as git
from metta.common.util.fs import get_repo_root
from metta.setup.utils import error, get_console, info, success, warning


@dataclass
class FormatterResult:
    success: bool
    output: str = ""
    processed_files: int = 0


CHECK_PYRIGHT_PACKAGES = [
    "agent",
    "app_backend",
    "common",
    "metta/gridworks",
    # "metta/rl",
    "packages/cogames",
    "packages/mettagrid/python/src",  # mettagrid/tests is not type-safe yet
]


FileLinterRunner = Callable[[bool, set[str], bool], FormatterResult]
ProjectCheckRunner = Callable[[bool], FormatterResult]


class FileLinter(BaseModel):
    name: str
    check_cmds: tuple[tuple[str, ...], ...] = ()
    format_cmds: tuple[tuple[str, ...], ...] = ()
    extensions: tuple[str, ...] = ()
    runner: FileLinterRunner | None = None
    required_binaries: tuple[str, ...] = ()

    def run(self, fix: bool, files: set[str], is_full_run: bool) -> FormatterResult:
        if self.runner is not None:
            return self.runner(fix, files, is_full_run)
        commands = self.format_cmds if fix else self.check_cmds
        if not commands:
            return FormatterResult(success=True, processed_files=len(files))
        file_count = len(files)
        file_args = sorted(files)
        for base_cmd in commands:
            cmd = list(base_cmd) + file_args
            result = subprocess.run(
                cmd,
                cwd=get_repo_root(),
                check=False,
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                return FormatterResult(
                    success=False,
                    output=result.stderr + result.stdout,
                    processed_files=file_count,
                )
        return FormatterResult(success=True, processed_files=file_count)


class ProjectCheck(BaseModel):
    name: str
    check_cmd: tuple[str, ...] | None = None
    fix_cmd: tuple[str, ...] | None = None
    extensions: tuple[str, ...] = ()
    runner: ProjectCheckRunner | None = None
    required_binaries: tuple[str, ...] = ()

    def run(self, fix: bool) -> FormatterResult:
        if self.runner is not None:
            return self.runner(fix)
        assert self.check_cmd is not None
        cmd = list(self.fix_cmd) if fix and self.fix_cmd else list(self.check_cmd)
        result = subprocess.run(
            cmd,
            cwd=get_repo_root(),
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return FormatterResult(
                success=False,
                output=result.stderr + result.stdout,
            )
        return FormatterResult(success=True)


def _normalize_extensions(extensions: Sequence[str]) -> tuple[str, ...]:
    normalized = []
    for ext in extensions:
        normalized.append(ext if ext.startswith(".") else f".{ext}")
    return tuple(normalized)


def _resolve_target_files(files: Optional[Sequence[str]], staged: bool) -> list[str]:
    repo_root = get_repo_root()
    normalized: list[str] = []
    seen: set[str] = set()
    if files is not None:
        raw_files = list(files)
    else:
        assert staged
        raw_files = [
            fname for status, fname in git.get_uncommitted_files_and_statuses() if status[0] in ("M", "A", "R")
        ]

    for raw in raw_files:
        if not raw:
            continue
        path = Path(raw)
        if path.is_absolute():
            try:
                path = path.relative_to(repo_root)
            except ValueError:
                path = path.resolve()
        rel = path.as_posix()
        if rel in seen:
            continue
        seen.add(rel)
        if not (repo_root / rel).exists():
            continue
        normalized.append(rel)
    return normalized


def _collect_prettier_targets(
    extensions: Sequence[str],
    files: set[str],
    exclude_patterns: Sequence[str],
) -> list[str]:
    normalized_exts = _normalize_extensions(extensions)
    repo_root = get_repo_root()
    candidates = []
    for candidate in sorted(files):
        if Path(candidate).suffix.lower() not in normalized_exts:
            continue
        if not (repo_root / candidate).exists():
            continue
        if exclude_patterns and any(pattern in candidate for pattern in exclude_patterns):
            continue
        candidates.append(candidate)
    return candidates


def _format_progress_message(formatter_name: str, action: str, file_count: int | None, color: str) -> str:
    suffix = f" {file_count} file(s)" if file_count else ""
    return f"[{color}]{formatter_name} • {action}{suffix}[/]"


def _make_cpp_runner() -> ProjectCheckRunner:
    def _runner(fix: bool) -> FormatterResult:
        repo_root = get_repo_root()
        mettagrid_dir = repo_root / "packages" / "mettagrid"

        # Find all C/C++ files in the target directories
        cpp_extensions = (".c", ".h", ".cpp", ".hpp")
        target_dirs = ["cpp/src", "cpp/include", "tests", "benchmarks"]
        cpp_files: list[str] = []

        for target_dir in target_dirs:
            dir_path = mettagrid_dir / target_dir
            if not dir_path.exists():
                continue
            for ext in cpp_extensions:
                cpp_files.extend(str(f) for f in dir_path.rglob(f"*{ext}"))

        if not cpp_files:
            return FormatterResult(success=True, processed_files=0)

        if fix:
            cmd = ["clang-format", "-i", "-style=file", *cpp_files]
        else:
            cmd = ["clang-format", "--dry-run", "--Werror", "-style=file", *cpp_files]

        result = subprocess.run(
            cmd,
            cwd=mettagrid_dir,
            check=False,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            return FormatterResult(
                success=False,
                output=result.stderr + result.stdout,
                processed_files=len(cpp_files),
            )

        return FormatterResult(success=True, processed_files=len(cpp_files))

    return _runner


def _make_prettier_runner(
    *,
    extensions: Sequence[str],
    exclude_patterns: Sequence[str] = (),
) -> FileLinterRunner:
    normalized_exts = _normalize_extensions(extensions)

    def _runner(fix: bool, files: set[str], is_full_run: bool = False) -> FormatterResult:
        mode_arg = "--write" if fix else "--check"

        if is_full_run:
            globs = [f"**/*{ext}" for ext in normalized_exts]
            negations = [f"!**{pat}**" if pat.startswith("/") else f"!{pat}**" for pat in exclude_patterns]
            cmd = [
                "pnpm",
                "exec",
                "prettier",
                "--log-level",
                "warn",
                "--no-error-on-unmatched-pattern",
                mode_arg,
                *globs,
                *negations,
            ]
            result = subprocess.run(cmd, cwd=get_repo_root(), check=False, capture_output=True, text=True)
            if result.returncode != 0:
                return FormatterResult(success=False, output=result.stderr + result.stdout)
            return FormatterResult(success=True)

        targets = _collect_prettier_targets(extensions, files, exclude_patterns)
        if not targets:
            return FormatterResult(success=True, processed_files=0)

        def _chunked(items: Sequence[str], size: int) -> Iterable[Sequence[str]]:
            for start in range(0, len(items), size):
                yield items[start : start + size]

        processed = len(targets)
        for chunk in _chunked(targets, 100):
            cmd = ["pnpm", "exec", "prettier", "--log-level", "warn", mode_arg, *chunk]
            result = subprocess.run(
                cmd,
                cwd=get_repo_root(),
                check=False,
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                return FormatterResult(
                    success=False,
                    output=result.stderr + result.stdout,
                    processed_files=processed,
                )

        return FormatterResult(success=True, processed_files=processed)

    return _runner


def _make_turbo_js_runner(
    extensions: Sequence[str],
) -> FileLinterRunner:
    def _runner(fix: bool, files: set[str], is_full_run: bool = False) -> FormatterResult:
        repo_root = get_repo_root()
        normalized_exts = _normalize_extensions(extensions)

        if is_full_run:
            # Full runs use turbo to get caching and run all package lint/format scripts
            task = "format" if fix else "lint"
            cmd = ["pnpm", "exec", "turbo", task]
        elif files:
            # File-specific operations use prettier directly (turbo runs all packages
            # which causes issues when packages like gridworks can't handle external paths)
            targets = [f for f in files if Path(f).suffix.lower() in normalized_exts]
            if not targets:
                return FormatterResult(success=True, processed_files=0)
            mode_arg = "--write" if fix else "--check"
            cmd = ["pnpm", "exec", "prettier", "--log-level", "warn", mode_arg, *targets]
        else:
            return FormatterResult(success=True, processed_files=0)

        result = subprocess.run(
            cmd,
            cwd=repo_root,
            check=False,
            capture_output=True,
            text=True,
        )
        file_count = len(files) if files else 0
        if result.returncode != 0:
            return FormatterResult(
                success=False,
                output=result.stderr + result.stdout,
                processed_files=file_count,
            )
        return FormatterResult(success=True, processed_files=file_count)

    return _runner


def get_file_linters() -> list[FileLinter]:
    return [
        FileLinter(
            name="Python",
            format_cmds=(
                ("uv", "run", "--no-sync", "ruff", "check", "--fix", "--force-exclude"),
                ("uv", "run", "--no-sync", "ruff", "format", "--force-exclude"),
            ),
            check_cmds=(
                ("uv", "run", "--no-sync", "ruff", "check", "--force-exclude"),
                ("uv", "run", "--no-sync", "ruff", "format", "--check", "--force-exclude"),
            ),
            extensions=(".py",),
        ),
        FileLinter(
            name="JSON",
            extensions=(".json", ".jsonc", ".code-workspace"),
            required_binaries=("pnpm",),
            runner=_make_prettier_runner(
                extensions=(".json", ".jsonc", ".code-workspace"),
                exclude_patterns=(
                    "/charts/",
                    "packages/mettagrid/python/src/mettagrid/renderer/assets/",
                    "packages/mettagrid/nim/mettascope/data/",
                    ".import_linter_cache/",
                    ".grimp_cache/",
                    "app_backend/src/metta/app_backend/generated/",
                ),
            ),
        ),
        FileLinter(
            name="Shell",
            extensions=(".sh", ".bash"),
            required_binaries=("pnpm",),
            runner=_make_prettier_runner(
                extensions=(".sh", ".bash"),
            ),
        ),
        FileLinter(
            name="TOML",
            extensions=(".toml",),
            required_binaries=("pnpm",),
            runner=_make_prettier_runner(
                extensions=(".toml",),
            ),
        ),
        FileLinter(
            name="YAML",
            extensions=(".yaml", ".yml"),
            required_binaries=("pnpm",),
            runner=_make_prettier_runner(
                extensions=(".yaml", ".yml"),
                exclude_patterns=(
                    "/configs/",
                    "/scenes/",
                    "/charts/",
                    ".github/actions/asana/pr_gh_to_asana/test/",
                ),
            ),
        ),
        FileLinter(
            name="Javascript",
            extensions=(".ts", ".tsx", ".js", ".jsx"),
            required_binaries=("pnpm",),
            runner=_make_turbo_js_runner(extensions=(".ts", ".tsx", ".js", ".jsx")),
        ),
    ]


def get_project_checks() -> list[ProjectCheck]:
    return [
        ProjectCheck(
            name="Pyright",
            check_cmd=("uv", "run", "--no-sync", "pyright", *CHECK_PYRIGHT_PACKAGES),
            extensions=(".py",),
        ),
        ProjectCheck(
            name="Python Import Linter",
            check_cmd=("env", "GRIMP_PURE_PYTHON=1", "uv", "run", "--no-sync", "lint-imports"),
            extensions=(".py",),
        ),
        ProjectCheck(
            name="C++",
            extensions=(".cpp", ".hpp", ".h", ".c"),
            required_binaries=("clang-format",),
            runner=_make_cpp_runner(),
        ),
        ProjectCheck(
            name="TypeScript Type Check",
            check_cmd=("pnpm", "exec", "turbo", "type-check"),
            extensions=(".ts", ".tsx"),
            required_binaries=("pnpm",),
        ),
    ]


app = typer.Typer(
    help="Code formatters",
    invoke_without_command=True,
)


@app.callback()
def cmd_lint(
    files: Annotated[Optional[list[str]], typer.Argument()] = None,
    staged: Annotated[bool, typer.Option("--staged", help="Only lint staged files")] = False,
    fix: Annotated[bool, typer.Option("--fix", help="Apply fixes automatically")] = False,
    verbose: Annotated[bool, typer.Option("--verbose", help="Print total lint time")] = False,
):
    """Run linting and formatting on code files.

    Examples:
        metta lint                                     # Check all files
        metta lint --fix                               # Autofix all files
        metta lint --staged --fix                      # Autofix staged files
        metta lint path/to/file1 path/to/file2 --fix   # Autofix specific files
    """
    start_time = time.perf_counter()
    is_full_run = not files and not staged

    file_linters = get_file_linters()

    if is_full_run:
        files_by_linter: dict[str, set[str]] = {}
        all_runners: list[FileLinter | ProjectCheck] = file_linters + get_project_checks()
    else:
        target_files = _resolve_target_files(files, staged)
        _fbl = defaultdict(set)
        for f in target_files:
            ext = Path(f).suffix.lower()
            for linter in file_linters:
                if ext in linter.extensions:
                    _fbl[linter.name].add(f)
        files_by_linter = dict(_fbl)
        all_runners = [fl for fl in file_linters if files_by_linter.get(fl.name)]
        if not all_runners:
            info("No matching files to lint.")
            if verbose:
                elapsed = time.perf_counter() - start_time
                info(f"Lint finished in {elapsed:.2f}s")
            return

    for runner in list(all_runners):
        if not runner.required_binaries:
            continue
        missing = [b for b in runner.required_binaries if shutil.which(b) is None]
        if missing:
            warning(f"Skipping {runner.name}: {', '.join(missing)} not found. Run: metta install")
            all_runners.remove(runner)
            files_by_linter.pop(runner.name, None)

    failed_formatters: list[tuple[str, str]] = []
    columns = (
        SpinnerColumn(style="cyan"),
        TextColumn("{task.description}", justify="left"),
    )

    with Progress(*columns, transient=True, console=get_console()) as progress:
        with ThreadPoolExecutor(max_workers=len(all_runners) or 1) as executor:
            futures = {}
            for runner in all_runners:
                action_word = "Formatting" if fix else "Checking"
                if isinstance(runner, FileLinter):
                    fs = files_by_linter.get(runner.name, set())
                    file_count = len(fs) or None
                    desc = _format_progress_message(runner.name, action_word, file_count, "blue")
                    task_id = progress.add_task(desc, total=None, start=True)
                    future = executor.submit(runner.run, fix=fix, files=fs, is_full_run=is_full_run)
                else:
                    file_count = None
                    desc = _format_progress_message(runner.name, action_word, file_count, "blue")
                    task_id = progress.add_task(desc, total=None, start=True)
                    future = executor.submit(runner.run, fix=fix)
                futures[future] = (runner, task_id, file_count)

            for future in as_completed(futures):
                runner, task_id, planned_count = futures[future]
                result = future.result()
                if result.success:
                    progress.remove_task(task_id)
                else:
                    processed = result.processed_files or planned_count
                    final_action = "Formatted" if fix else "Checked"
                    final_desc = _format_progress_message(runner.name, final_action, processed, "red")
                    progress.update(task_id, description=final_desc)
                    progress.stop_task(task_id)
                    failed_formatters.append((runner.name, result.output))

    if failed_formatters:
        error(f"Linting/formatting failed for: {', '.join(name for name, _ in failed_formatters)}")
        for formatter_name, output in failed_formatters:
            if output:
                typer.echo(f"\n[{formatter_name} output]\n{output}\n")
        raise typer.Exit(1)
    else:
        success("All formatting complete")

    if verbose:
        elapsed = time.perf_counter() - start_time
        info(f"Lint finished in {elapsed:.2f}s")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
