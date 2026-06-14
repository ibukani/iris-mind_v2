"""v0.1ターゲットアーキテクチャのアンチパターンスキャンと機能境界ルール。

適用されるルール:
  1. 新しいターゲットモジュールにグローバル可変レジストリがないこと。
  2. 新しいターゲットモジュールにサービスロケータアクセスパターンがないこと。
  3. contracts/に未型付けのdict[str, Any]公開契約がないこと。
  4. 新しいターゲットモジュールにaction: strディスパッチャパターンがないこと。
  5. cognitive/presentation/safety/contracts/core内にアプリ固有のインポートがないこと。
  6. 機能はコアオーケストレーションではなくFeatureDefinitionを使用すること。
  7. 機能はWorkspaceFrameを直接変更してはならない。
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# Target directories to scan for anti-patterns.
TARGET_DIRS: list[str] = [
    "iris/contracts",
    "iris/core",
    "iris/cognitive",
    "iris/presentation",
    "iris/safety",
    "iris/features",
    "iris/adapters",
    "iris/runtime",
]

# App-specific keywords that should not appear in core layers.
APP_SPECIFIC_KEYWORDS: set[str] = {
    "discord",
    "discord.py",
    "nextcord",
    "py-cord",
    "speechd",
    "azure.cognitiveservices.speech",
    "elevenlabs",
    "openai.whisper",
    "vosk",
    "aiohttp",
    "flask",
    "fastapi",
    "starlette",
    "tortoise",
    "orator",
    "sqlalchemy.ext",
}


def _target_exists(rel_dir: str) -> bool:
    return (PROJECT_ROOT / rel_dir).is_dir()


def _get_python_files(base: Path) -> list[Path]:
    return sorted(base.rglob("*.py"))


def _get_imports(filepath: Path) -> list[str]:
    try:
        tree = ast.parse(filepath.read_text(encoding="utf-8"))
    except SyntaxError:
        return []
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
    return imports


def _module_level_mutable_objects(tree: ast.Module) -> list[str]:
    """モジュールレベルの可変オブジェクト（レジスタ、グローバルdictなど）を検出する。

    Returns:
        list[str]: 発見された可変オブジェクトの説明リスト。
    """
    findings: list[str] = []
    for node in ast.iter_child_nodes(tree):
        # Module-level assignments of mutable types
        if isinstance(node, ast.Assign):
            findings.extend(
                f"global mutable '{target.id}'"
                for target in node.targets
                if isinstance(target, ast.Name)
                and target.id.isupper()
                and isinstance(node.value, (ast.Dict, ast.List, ast.Set))
            )
        # Module-level function calls like register(), subscribe()
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            func = node.value.func
            if isinstance(func, ast.Attribute) and func.attr in {
                "register",
                "subscribe",
                "add_hook",
            }:
                findings.append(f"module-level call: {ast.unparse(func)}")
            elif isinstance(func, ast.Name) and func.id in {"register", "subscribe", "add_hook"}:
                findings.append(f"module-level call: {func.id}()")
    return findings


def _has_action_str_dispatch(tree: ast.Module) -> list[str]:
    """action: strディスパッチャパターン（文字列を比較するif/elifチェーン）を検出する。

    Returns:
        list[str]: 発見された文字列ディスパッチャパターンの説明リスト。
    """
    findings: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            _check_if_for_string_dispatch(node, findings)
        # match/case on strings
        if isinstance(node, ast.Match):
            subject = node.subject
            # Check if matching on a simple name like "action" or "action_type"
            if isinstance(subject, ast.Name) and subject.id in {
                "action",
                "action_type",
                "event_type",
                "command",
            }:
                findings.extend(
                    f"match/case dispatch on string '{case.pattern.value.value!r}'"
                    for case in node.cases
                    if isinstance(case.pattern, ast.MatchValue)
                    and isinstance(case.pattern.value, ast.Constant)
                )
    return findings


def _get_compare_str(comparison: ast.Compare | None) -> str | None:
    """AST Compareノードからディスパッチ対象の文字列値を抽出する。

    Returns:
        ディスパッチ対象の文字列値。該当しない場合はNone。
    """
    if comparison is None:
        return None
    if isinstance(comparison.left, ast.Name) and comparison.left.id in {
        "action",
        "action_type",
        "command",
    }:
        for op, right in zip(comparison.ops, comparison.comparators, strict=False):
            if (
                isinstance(op, (ast.Eq, ast.Is))
                and isinstance(right, ast.Constant)
                and isinstance(right.value, str)
            ):
                return str(right.value)
    return None


def _check_if_for_string_dispatch(node: ast.If, findings: list[str]) -> None:
    """if-elifチェーンを再帰的にチェックして文字列比較ディスパッチを検出する。"""
    if isinstance(node.test, ast.Compare):
        val = _get_compare_str(node.test)
        if val:
            findings.append(f"if/elif dispatch on '{val}'")

    for child in ast.walk(node):
        if isinstance(child, ast.If) and isinstance(child.test, ast.Compare):
            val = _get_compare_str(child.test)
            if val:
                findings.append(f"if/elif dispatch on '{val}'")


# ── 1. Global mutable registries ───────────────────────────────


@pytest.mark.parametrize("target_dir", sorted(TARGET_DIRS))
def test_no_global_mutable_registries(target_dir: str) -> None:
    """新しいターゲットモジュールにグローバル可変レジストリを含めてはならない。"""
    if not _target_exists(target_dir):
        pytest.skip(f"Target layer '{target_dir}' does not exist yet")
    base = PROJECT_ROOT / target_dir
    violations: list[str] = []
    for filepath in _get_python_files(base):
        try:
            tree = ast.parse(filepath.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        findings = _module_level_mutable_objects(tree)
        if findings:
            rel = filepath.relative_to(PROJECT_ROOT).as_posix()
            violations.append(f"  {rel}: {', '.join(findings)}")
    assert not violations, f"Global mutable registries found in {target_dir}:\n" + "\n".join(
        violations
    )


# ── 2. Service locator patterns ────────────────────────────────


@pytest.mark.parametrize("target_dir", sorted(TARGET_DIRS))
def test_no_service_locator_patterns(target_dir: str) -> None:
    """新しいターゲットモジュールはサービスロケータアクセスパターンを使用してはならない。"""
    if not _target_exists(target_dir):
        pytest.skip(f"Target layer '{target_dir}' does not exist yet")

    forbidden_imports = {
        "iris.kernel.manager",
    }
    forbidden_names = {"resolve", "get_service", "locate", "container"}

    base = PROJECT_ROOT / target_dir
    violations: list[str] = []
    for filepath in _get_python_files(base):
        rel = filepath.relative_to(PROJECT_ROOT).as_posix()
        try:
            text = filepath.read_text(encoding="utf-8")
            tree = ast.parse(text)
        except (SyntaxError, FileNotFoundError):
            continue

        # Check imports
        violations.extend(
            f"  {rel}: imports '{imp}' (service locator)"
            for imp in _get_imports(filepath)
            for f in forbidden_imports
            if imp.startswith(f)
        )

        # Check function calls
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                name_parts: list[str] = []
                cur = func
                while isinstance(cur, ast.Attribute):
                    name_parts.insert(0, cur.attr)
                    cur = cur.value
                if isinstance(cur, ast.Name):
                    name_parts.insert(0, cur.id)
                full_name = ".".join(name_parts)
                violations.extend(
                    f"  {rel}:{node.lineno} calls '{full_name}' (service locator)"
                    for fn in forbidden_names
                    if fn in name_parts and full_name != "TypeVar.resolve"
                )

    assert not violations, f"Service locator patterns found in {target_dir}:\n" + "\n".join(
        violations
    )


# ── 3. Untyped dict contracts ────────────────────────────────


def _annassign_has_forbidden_dict(node: ast.AnnAssign, forbidden: set[str]) -> bool:
    """Return whether an AnnAssign annotation contains a forbidden dict pattern."""
    ann_str = ast.unparse(node.annotation).lower().replace(" ", "")
    return any(f.lower().replace(" ", "") in ann_str for f in forbidden)


def _format_violation(filepath: Path, node: ast.stmt) -> str:
    """Format a single dict-pattern violation message for a node.

    Args:
        filepath: Path of the file containing the violation.
        node: AST node whose line is being reported.

    Returns:
        str: A two-space-indented, relative-pathed message line.
    """
    rel = filepath.relative_to(PROJECT_ROOT).as_posix()
    line = filepath.read_text(encoding="utf-8").splitlines()[node.lineno - 1]
    return f"  {rel}:{node.lineno} {line.strip()}"


def test_contracts_no_untyped_dict_public_api() -> None:
    """公開契約はフィールド型としてdict[str, Any]やdict[str, object]を使用してはならない。

    iris/contracts/内で未型付けdictで注釈されたdataclassフィールドをスキャンする。
    """
    contracts_dir = PROJECT_ROOT / "iris" / "contracts"
    if not contracts_dir.is_dir():
        pytest.skip("iris/contracts/ does not exist yet")

    forbidden = {"dict[str, Any]", "dict[str, object]", "Dict[str, Any]", "Dict[str, object]"}
    violations: list[str] = []

    for filepath in _get_python_files(contracts_dir):
        try:
            tree = ast.parse(filepath.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        violations.extend(
            _format_violation(filepath, node)
            for node in ast.walk(tree)
            if isinstance(node, ast.AnnAssign) and _annassign_has_forbidden_dict(node, forbidden)
        )

    assert not violations, "Untyped dict[str, Any] in public contracts:\n" + "\n".join(violations)


# ── 4. action: str dispatcher ───────────────────────────────


@pytest.mark.parametrize("target_dir", sorted(TARGET_DIRS))
def test_no_action_str_dispatch(target_dir: str) -> None:
    """新しいターゲットモジュールはaction: strディスパッチャブランチを追加してはならない。"""
    if not _target_exists(target_dir):
        pytest.skip(f"Target layer '{target_dir}' does not exist yet")

    base = PROJECT_ROOT / target_dir
    violations: list[str] = []
    for filepath in _get_python_files(base):
        try:
            tree = ast.parse(filepath.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        findings = _has_action_str_dispatch(tree)
        if findings:
            rel = filepath.relative_to(PROJECT_ROOT).as_posix()
            violations.extend(f"  {rel}: {f}" for f in findings)

    assert not violations, f"action: str dispatcher patterns in {target_dir}:\n" + "\n".join(
        violations
    )


# ── 5. App-specific imports in core layers ─────────────────────


@pytest.mark.parametrize(
    "layer_dir",
    ["iris/cognitive", "iris/presentation", "iris/safety", "iris/contracts", "iris/core"],
)
def test_no_app_specific_imports_in_core_layers(layer_dir: str) -> None:
    """コア層はアプリ固有のパッケージをインポートしてはならない。"""
    if not _target_exists(layer_dir):
        pytest.skip(f"Layer '{layer_dir}' does not exist yet")

    base = PROJECT_ROOT / layer_dir
    violations: list[str] = []
    for filepath in _get_python_files(base):
        for imp in _get_imports(filepath):
            imp_lower = imp.lower()
            for keyword in APP_SPECIFIC_KEYWORDS:
                if keyword in imp_lower:
                    rel = filepath.relative_to(PROJECT_ROOT).as_posix()
                    violations.append(f"  {rel}: imports '{imp}' (app-specific: {keyword})")
                    break

    assert not violations, f"App-specific imports in {layer_dir}:\n" + "\n".join(violations)


# ── 6. Feature boundary rules ──────────────────────────────────


def test_features_use_definition_pattern() -> None:
    """機能は登録にFeatureDefinitionを使用しなければならない。

    iris/features/内のdefine_feature()呼び出しやFeatureDefinitionの使用をスキャンする。
    コグニティブ内部に直接インポートまたは登録する__init__.pyやfeature.pyは違反とする。
    """
    features_dir = PROJECT_ROOT / "iris" / "features"
    if not features_dir.is_dir():
        pytest.skip("iris/features/ does not exist yet")

    violations: list[str] = []

    for filepath in _get_python_files(features_dir):
        rel = filepath.relative_to(PROJECT_ROOT).as_posix()
        try:
            text = filepath.read_text(encoding="utf-8")
        except OSError:
            continue

        # Check that every feature.py uses FeatureDefinition
        if (
            filepath.name == "feature.py"
            and "FeatureDefinition" not in text
            and "define_feature" not in text
        ):
            violations.append(
                f"  {rel}: feature.py does not use FeatureDefinition or define_feature()"
            )

        # Check for direct cognitive internal access
        for imp in _get_imports(filepath):
            if not imp.startswith(("iris.cognitive.cycle", "iris.cognitive.workspace")):
                continue
            # FeatureDefinition is architecturally allowed to import cognitive
            # extension protocols (PipelineStep, PipelineStepResult) from cognitive/cycle/
            # and the WorkspaceFrame type referenced by those protocols.
            if filepath.name == "definition.py" and (
                imp.startswith("iris.cognitive.cycle") or imp == "iris.cognitive.workspace.frame"
            ):
                continue
            violations.append(
                f"  {rel}: imports '{imp}' — features must not import cognitive internals"
            )

    assert not violations, "Feature boundary violations:\n" + "\n".join(violations)


def test_features_no_direct_frame_mutation() -> None:
    """機能はWorkspaceFrameを直接変更してはならない。

    features/内のWorkspaceFrameのインポートは、FrameBuilderまたはCognitiveCycleを介した読み取り専用であり、
    直接変更してはならない。
    """
    features_dir = PROJECT_ROOT / "iris" / "features"
    if not features_dir.is_dir():
        pytest.skip("iris/features/ does not exist yet")

    violations: list[str] = []
    for filepath in _get_python_files(features_dir):
        rel = filepath.relative_to(PROJECT_ROOT).as_posix()
        try:
            tree = ast.parse(filepath.read_text(encoding="utf-8"))
        except SyntaxError:
            continue

        # Check for frame attribute assignment
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                violations.extend(
                    f"  {rel}: mutates WorkspaceFrame directly"
                    for target in node.targets
                    if isinstance(target, ast.Attribute)
                    and isinstance(target.value, ast.Name)
                    and target.value.id == "frame"
                )

    assert not violations, "Direct WorkspaceFrame mutation from features:\n" + "\n".join(violations)


# ── 7. Adapter port boundaries ──────────────────────────────────


def test_cognitive_does_not_import_adapter_implementations() -> None:
    """cognitive/は具象アダプター実装をインポートしてはならない。

    cognitive/はadapters/.../ports.py（ポート/プロトコル）からのみインポートでき、
    fake.py、openai.py、langchain.py、vector.pyなどの具象アダプターファイルからはインポートしてはならない。
    """
    cognitive_dir = PROJECT_ROOT / "iris" / "cognitive"
    if not cognitive_dir.is_dir():
        pytest.skip("iris/cognitive/ does not exist yet")

    adapter_concrete_files = {
        "iris.adapters.llm.fake",
        "iris.adapters.llm.openai",
        "iris.adapters.memory.fake",
        "iris.adapters.memory.langchain",
        "iris.adapters.memory.vector",
    }

    violations: list[str] = []
    for filepath in _get_python_files(cognitive_dir):
        rel = filepath.relative_to(PROJECT_ROOT).as_posix()
        violations.extend(
            f"  {rel}: imports concrete adapter '{imp}' — use a port/protocol instead"
            for imp in _get_imports(filepath)
            if imp in adapter_concrete_files
        )

    assert not violations, (
        "cognitive/ must not import concrete adapter implementations:\n" + "\n".join(violations)
    )


def test_cognitive_memory_defines_own_port() -> None:
    """Cognitive/memory/は独自のMemoryRetrieverプロトコルを定義しなければならない。"""
    memory_retrieval = PROJECT_ROOT / "iris" / "cognitive" / "memory" / "retrieval.py"
    if not memory_retrieval.is_file():
        pytest.skip("iris/cognitive/memory/retrieval.py does not exist yet")

    text = memory_retrieval.read_text(encoding="utf-8")
    tree = ast.parse(text)

    imports = _get_imports(memory_retrieval)
    for imp in imports:
        assert not imp.startswith("iris.adapters.memory"), (
            f"cognitive/memory/retrieval.py imports '{imp}'"
            " — must define its own port (MemoryRetriever protocol)"
        )

    has_port = False
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "MemoryRetriever":
            has_port = True
            break
    assert has_port, "cognitive/memory/retrieval.py must define a MemoryRetriever protocol"


def test_cognitive_action_defines_own_port() -> None:
    """Cognitive/action/は独自のResponseGeneratorプロトコルを定義しなければならない。"""
    action_response = PROJECT_ROOT / "iris" / "cognitive" / "action" / "response.py"
    if not action_response.is_file():
        pytest.skip("iris/cognitive/action/response.py does not exist yet")

    imports = _get_imports(action_response)
    for imp in imports:
        assert not imp.startswith("iris.adapters.llm"), (
            f"cognitive/action/response.py imports '{imp}'"
            " — must define its own port (ResponseGenerator protocol)"
        )

    tree = ast.parse(action_response.read_text(encoding="utf-8"))
    has_port = False
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "ResponseGenerator":
            has_port = True
            break
    assert has_port, "cognitive/action/response.py must define a ResponseGenerator protocol"


# ── 8. Untyped dict boundaries expanded ────────────────────────


LAYERS_WITH_TYPED_BOUNDARIES: list[str] = [
    "iris/cognitive",
    "iris/features",
    "iris/presentation",
    "iris/safety",
]

FORBIDDEN_DICT_PATTERNS: set[str] = {
    "dict[str, Any]",
    "dict[str, object]",
    "Dict[str, Any]",
    "Dict[str, object]",
    "MutableMapping",
}


def _collect_func_param_dict_violations(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    rel: str,
) -> list[str]:
    """関数パラメータの型注釈から禁止dictパターンを収集する。

    Returns:
        違反メッセージのリスト。
    """
    violations: list[str] = []
    for arg in node.args.args:
        if arg.annotation is not None:
            ann_str = ast.unparse(arg.annotation)
            violations.extend(
                f"  {rel}:{node.lineno} parameter '{arg.arg}: {ann_str}'"
                for f in FORBIDDEN_DICT_PATTERNS
                if f in ann_str
            )
    return violations


def _collect_file_dict_violations(filepath: Path) -> list[str]:
    """単一ファイルから未型付けdict違反を収集する。

    Returns:
        違反メッセージのリスト。
    """
    violations: list[str] = []
    rel = filepath.relative_to(PROJECT_ROOT).as_posix()
    try:
        tree = ast.parse(filepath.read_text(encoding="utf-8"))
    except SyntaxError:
        return violations

    for node in ast.walk(tree):
        if not isinstance(node, ast.stmt):
            continue
        node_line: int = node.lineno

        if isinstance(node, ast.AnnAssign):
            ann_str = ast.unparse(node.annotation)
            for f in FORBIDDEN_DICT_PATTERNS:
                if f in ann_str:
                    lines = filepath.read_text(encoding="utf-8").splitlines()
                    line_text: str = lines[node_line - 1].strip()
                    violations.append(f"  {rel}:{node_line} {line_text}")
                    break
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            violations.extend(_collect_func_param_dict_violations(node, rel))

    return violations


def test_internal_layers_no_untyped_dict() -> None:
    """すべての内部層は型付き境界内で未型付けのdict/mappingを避けなければならない。

    dataclassフィールド注釈と関数シグネチャの
    dict[str, Any]、dict[str, object]、MutableMappingの使用をチェックする。
    """
    violations: list[str] = []

    for layer_dir in LAYERS_WITH_TYPED_BOUNDARIES:
        base = PROJECT_ROOT / layer_dir
        if not base.is_dir():
            continue
        for filepath in _get_python_files(base):
            violations.extend(_collect_file_dict_violations(filepath))

    assert not violations, (
        "Internal layers must not use dict[str, Any]/dict[str, object]/MutableMapping:\n"
        + "\n".join(violations)
    )
