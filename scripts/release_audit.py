"""Run fast, network-free checks before publishing an Evalflow release."""

from __future__ import annotations

import ast
import re
import subprocess
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_DOCUMENTS = (
    "README.md",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "RELEASE_CHECKLIST.md",
    "docs/DEMO.md",
)
FORBIDDEN_DIRECTORIES = {
    ".pytest_cache",
    ".venv",
    "__pycache__",
    "node_modules",
}
FORBIDDEN_SECRET_NAMES = {
    ".env",
    ".env.production",
    "id_dsa",
    "id_ed25519",
    "id_rsa",
}
FORBIDDEN_SECRET_SUFFIXES = {".key", ".p12", ".pem", ".pfx"}
PRIVATE_KEY_PATTERN = re.compile(
    r"-----BEGIN (?:[A-Z0-9]+ )?PRIVATE KEY-----"
)
STUDENT_MARKER = "TODO" + "(student)"


@dataclass
class AuditReport:
    checks: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def passed(self, message: str) -> None:
        self.checks.append(message)

    def failed(self, message: str) -> None:
        self.errors.append(message)


def project_version(root: Path) -> str:
    with (root / "pyproject.toml").open("rb") as handle:
        metadata = tomllib.load(handle)
    return str(metadata["project"]["version"])


def repository_files(root: Path) -> list[Path]:
    completed = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    return [
        root / path.decode("utf-8")
        for path in completed.stdout.split(b"\0")
        if path
    ]


def _literal_assignment(tree: ast.Module, name: str) -> object:
    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        else:
            continue
        if any(isinstance(target, ast.Name) and target.id == name for target in targets):
            return ast.literal_eval(node.value)
    raise ValueError(f"missing {name!r} assignment")


def migration_graph(root: Path) -> tuple[set[str], set[str]]:
    migrations: dict[str, tuple[str, ...]] = {}
    for path in sorted((root / "alembic" / "versions").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        revision = _literal_assignment(tree, "revision")
        down_revision = _literal_assignment(tree, "down_revision")
        if not isinstance(revision, str) or not revision:
            raise ValueError(f"{path.name} has an invalid revision")
        if revision in migrations:
            raise ValueError(f"duplicate migration revision {revision}")
        if down_revision is None:
            parents: tuple[str, ...] = ()
        elif isinstance(down_revision, str):
            parents = (down_revision,)
        elif isinstance(down_revision, (tuple, list)) and all(
            isinstance(parent, str) for parent in down_revision
        ):
            parents = tuple(down_revision)
        else:
            raise ValueError(f"{path.name} has an invalid down_revision")
        migrations[revision] = parents

    revisions = set(migrations)
    referenced = {parent for parents in migrations.values() for parent in parents}
    missing = referenced - revisions
    heads = revisions - referenced
    return heads, missing


def _audit_version(root: Path, report: AuditReport, version: str) -> None:
    version_markers = {
        "backend/config.py": f'app_version: str = "{version}"',
        "frontend/package.json": f'"version": "{version}"',
        "frontend/package-lock.json": f'"version": "{version}"',
        ".github/workflows/deploy.yml": f'default: "{version}"',
        ".env.production.example": f"-api:{version}",
        "DEPLOYMENT.md": f"git tag -a v{version}",
    }
    failures_before = len(report.errors)
    for relative_path, marker in version_markers.items():
        path = root / relative_path
        if not path.is_file() or marker not in path.read_text(encoding="utf-8"):
            report.failed(f"Version {version} is not synchronized in {relative_path}")
    if len(report.errors) == failures_before:
        report.passed(f"Version {version} is synchronized across release assets")


def _audit_documents(root: Path, report: AuditReport) -> None:
    missing_documents = [
        name for name in REQUIRED_DOCUMENTS if not (root / name).is_file()
    ]
    if missing_documents:
        report.failed("Missing documentation: " + ", ".join(missing_documents))
    else:
        report.passed("Release, security, contribution, and demo documentation exists")


def _audit_migrations(root: Path, report: AuditReport) -> None:
    try:
        heads, missing_parents = migration_graph(root)
    except (OSError, SyntaxError, ValueError) as exc:
        report.failed(f"Cannot validate Alembic migrations: {exc}")
    else:
        if missing_parents:
            report.failed(
                "Alembic migrations reference missing revisions: "
                + ", ".join(sorted(missing_parents))
            )
        if len(heads) != 1:
            report.failed(
                f"Alembic must have exactly one head; found {len(heads)}: "
                + ", ".join(sorted(heads))
            )
        if not missing_parents and len(heads) == 1:
            report.passed(f"Alembic has one complete migration head: {next(iter(heads))}")


def _repository_hygiene_findings(
    root: Path,
    files: list[Path],
) -> tuple[list[str], list[str]]:
    unsafe_paths: list[str] = []
    findings: list[str] = []
    for path in files:
        relative = path.relative_to(root)
        lowered_parts = {part.lower() for part in relative.parts}
        if lowered_parts & FORBIDDEN_DIRECTORIES:
            unsafe_paths.append(relative.as_posix())
        is_unapproved_env = (
            path.name.lower().startswith(".env")
            and not path.name.lower().endswith(".example")
        )
        if (
            path.name.lower() in FORBIDDEN_SECRET_NAMES
            or path.suffix.lower() in FORBIDDEN_SECRET_SUFFIXES
            or is_unapproved_env
        ):
            unsafe_paths.append(relative.as_posix())
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for line_number, line in enumerate(text.splitlines(), start=1):
            stripped = line.lstrip()
            if stripped.startswith(("<<<<<<< ", ">>>>>>> ")):
                findings.append(f"{relative.as_posix()}:{line_number} merge marker")
            if STUDENT_MARKER in line:
                findings.append(f"{relative.as_posix()}:{line_number} student task")
        if PRIVATE_KEY_PATTERN.search(text):
            findings.append(f"{relative.as_posix()} contains a private key")
    return unsafe_paths, findings


def _audit_repository_hygiene(root: Path, report: AuditReport) -> bool:
    try:
        files = repository_files(root)
    except (OSError, subprocess.CalledProcessError) as exc:
        report.failed(f"Cannot list tracked files: {exc}")
        return False

    unsafe_paths, findings = _repository_hygiene_findings(root, files)

    if unsafe_paths:
        report.failed(
            "Unsafe generated or secret-like tracked paths: "
            + ", ".join(sorted(set(unsafe_paths)))
        )
    else:
        report.passed("No generated environments or secret-like files would be committed")
    if findings:
        report.failed("Repository hygiene findings: " + "; ".join(findings))
    else:
        report.passed("No private keys, merge markers, or student tasks were found")
    return True


def audit_repository(root: Path = ROOT) -> AuditReport:
    report = AuditReport()
    try:
        version = project_version(root)
    except (KeyError, OSError, tomllib.TOMLDecodeError) as exc:
        report.failed(f"Cannot read project version: {exc}")
        return report

    _audit_version(root, report, version)
    _audit_documents(root, report)
    _audit_migrations(root, report)
    _audit_repository_hygiene(root, report)
    return report


def main() -> int:
    report = audit_repository()
    print("Evalflow release audit")
    for check in report.checks:
        print(f"  PASS  {check}")
    for error in report.errors:
        print(f"  FAIL  {error}")
    if report.errors:
        print(f"Release audit failed with {len(report.errors)} finding(s).")
        return 1
    print(f"Ready to release v{project_version(ROOT)}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
