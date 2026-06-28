"""WorkspaceFrame、CognitiveCycle、PipelineStepの設計契約テスト。

適用されるルール:
  1. WorkspaceFrameはfrozen dataclassでなければならない。
  2. WorkspaceFrameのフィールドはdict[str, Any] / dict[str, object]を避けなければならない。
  3. フレームの更新はreplace()を使用してFrameBuilderを通さなければならない。
  4. CognitiveCycleはコーディネーターとして機能しなければならない
  （アダプター/ランタイム/機能のインポート禁止）。
  5. PipelineStepは型付きのPipelineStepResultサブタイプを返さなければならない。
  6. PipelineStepはアダプター、ランタイム配線、機能レジストリを直接呼び出してはならない。
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

TARGET_FILES: dict[str, Path] = {
    "workspace_frame": PROJECT_ROOT / "iris" / "cognitive" / "workspace" / "frame.py",
    "frame_builder": PROJECT_ROOT / "iris" / "cognitive" / "cycle" / "frame_builder.py",
    "cycle_service": PROJECT_ROOT / "iris" / "cognitive" / "cycle" / "service.py",
    "pipeline": PROJECT_ROOT / "iris" / "cognitive" / "cycle" / "pipeline.py",
    "cycle_models": PROJECT_ROOT / "iris" / "cognitive" / "cycle" / "models.py",
}


def _skip_if_missing(path: Path, label: str = "") -> None:
    if not path.is_file():
        pytest.skip(f"Target file not found: {path} ({label}) — test activates when implemented")


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _get_decorator_names(node: ast.AST) -> list[str]:
    names: list[str] = []
    for dec in getattr(node, "decorator_list", []):
        if isinstance(dec, ast.Name):
            names.append(dec.id)
        elif isinstance(dec, ast.Attribute):
            names.append(dec.attr)
        elif isinstance(dec, ast.Call) and isinstance(dec.func, ast.Name):
            names.append(dec.func.id)
        elif isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute):
            names.append(dec.func.attr)
    return names


def _find_class(tree: ast.Module, class_name: str) -> ast.ClassDef | None:
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return node
    return None


def _get_imports(tree: ast.Module) -> list[str]:
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
    return imports


def _class_has_frozen_dataclass(cls: ast.ClassDef) -> bool:
    for dec in cls.decorator_list:
        if (
            isinstance(dec, ast.Call)
            and isinstance(dec.func, ast.Name)
            and dec.func.id == "dataclass"
        ):
            for kw in dec.keywords:
                if (
                    kw.arg == "frozen"
                    and isinstance(kw.value, ast.Constant)
                    and kw.value.value is True
                ):
                    return True
        if isinstance(dec, ast.Attribute) and dec.attr == "dataclass":
            # @dataclass(frozen=True) called as attribute
            for kw in getattr(dec, "keywords", []):
                if (
                    kw.arg == "frozen"
                    and isinstance(kw.value, ast.Constant)
                    and kw.value.value is True
                ):
                    return True
    return False


def _class_has_dataclass(cls: ast.ClassDef) -> bool:
    for dec in cls.decorator_list:
        if (
            isinstance(dec, ast.Call)
            and isinstance(dec.func, ast.Name)
            and dec.func.id == "dataclass"
        ):
            return True
        if isinstance(dec, ast.Attribute) and dec.attr == "dataclass":
            return True
    return False


def _get_field_type_annotations(cls: ast.ClassDef) -> list[str]:
    """フィールド型注釈の文字列表現を返す。

    Returns:
        list[str]: フィールド型注釈の文字列表現リスト。
    """
    return [ast.unparse(item.annotation) for item in cls.body if isinstance(item, ast.AnnAssign)]


# ── 1. WorkspaceFrame immutability ─────────────────────────────


def test_workspace_frame_is_frozen_dataclass() -> None:
    """WorkspaceFrameはfrozen dataclassでなければならない。"""
    path = TARGET_FILES["workspace_frame"]
    _skip_if_missing(path)
    tree = _parse(path)
    cls = _find_class(tree, "WorkspaceFrame")
    assert cls is not None, "WorkspaceFrame class not found in frame.py"
    assert _class_has_frozen_dataclass(cls), (
        "WorkspaceFrame must be decorated with @dataclass(frozen=True)"
    )


def test_workspace_frame_no_dict_any_fields() -> None:
    """WorkspaceFrameにdict[str, Any]やdict[str, object]フィールドがあってはならない。"""
    path = TARGET_FILES["workspace_frame"]
    _skip_if_missing(path)
    tree = _parse(path)
    cls = _find_class(tree, "WorkspaceFrame")
    assert cls is not None, "WorkspaceFrame class not found"

    forbidden_types = {"dict[str, Any]", "dict[str, object]", "Dict[str, Any]", "Dict[str, object]"}
    field_types = _get_field_type_annotations(cls)
    violations = [t for t in field_types if t in forbidden_types]
    assert not violations, f"WorkspaceFrame uses forbidden untyped dict fields: {violations}"


def test_workspace_frame_no_mutable_mapping() -> None:
    """WorkspaceFrameはMutableMappingや可変デフォルトファクトリを使用してはならない。"""
    path = TARGET_FILES["workspace_frame"]
    _skip_if_missing(path)
    tree = _parse(path)
    cls = _find_class(tree, "WorkspaceFrame")
    assert cls is not None, "WorkspaceFrame class not found"

    text = path.read_text(encoding="utf-8")
    forbidden = {"MutableMapping", "dict", "list", "set"}
    for item in cls.body:
        if isinstance(item, ast.Assign):
            for target in item.targets:
                if isinstance(target, ast.Name):
                    for f in forbidden:
                        if f in text.splitlines()[item.lineno - 1]:
                            line = text.splitlines()[item.lineno - 1].strip()
                            if (
                                "tuple" not in line
                                and "field(default_factory=tuple" not in line
                                and "frozenset" not in line
                            ):
                                pytest.fail(
                                    f"WorkspaceFrame mutable default at L{item.lineno}: {line}"
                                )


# ── 2. FrameBuilder ────────────────────────────────────────────


def test_frame_builder_uses_replace() -> None:
    """FrameBuilder.applyはdataclasses.replace()を使用して新しいフレームを作成しなければならない。"""
    path = TARGET_FILES["frame_builder"]
    _skip_if_missing(path)
    tree = _parse(path)

    # Check FrameBuilder class exists
    cls = _find_class(tree, "FrameBuilder")
    assert cls is not None, "FrameBuilder class not found"

    # Check that replace() is called inside the class
    has_replace = False
    for node in ast.walk(cls):
        if isinstance(node, ast.Call):
            func = node.func
            if (isinstance(func, ast.Attribute) and func.attr == "replace") or (
                isinstance(func, ast.Name) and func.id == "replace"
            ):
                has_replace = True

    assert has_replace, "FrameBuilder must use dataclasses.replace() — no replace() call found"

    # Check no direct frame attribute mutation (frame.x = ...)
    for node in ast.walk(cls):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if (
                    isinstance(target, ast.Attribute)
                    and isinstance(target.value, ast.Name)
                    and target.value.id == "frame"
                ):
                    pytest.fail(f"FrameBuilder must not mutate frame directly (line {node.lineno})")


# ── 3. CognitiveCycle coordinator role ─────────────────────────


@pytest.mark.parametrize(
    "forbidden_prefix",
    [
        "iris.adapters",
        "iris.runtime",
        "iris.features",
        "iris.kernel.manager",
        "iris.event",
    ],
)
def test_cognitive_cycle_no_forbidden_imports(forbidden_prefix: str) -> None:
    """CognitiveCycleはアダプター、ランタイム、機能からインポートしてはならない。"""
    path = TARGET_FILES["cycle_service"]
    _skip_if_missing(path)
    tree = _parse(path)
    imports = _get_imports(tree)
    violations = [i for i in imports if i.startswith(forbidden_prefix)]
    assert not violations, (
        f"CognitiveCycle imports '{forbidden_prefix}' — coordinator must not depend on "
        f"adapters/runtime/features: {violations}"
    )


@pytest.mark.parametrize(
    "app_name", ["discord", "discord.py", "speech", "tts", "stt", "aiohttp", "flask", "fastapi"]
)
def test_cognitive_cycle_no_app_specific_imports(app_name: str) -> None:
    """CognitiveCycleはアプリ固有またはIOパッケージを直接インポートしてはならない。"""
    path = TARGET_FILES["cycle_service"]
    _skip_if_missing(path)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        pytest.skip("CognitiveCycle service.py does not exist yet")
    if app_name in text:
        pytest.fail(f"CognitiveCycle depends on '{app_name}' — no app/IO imports allowed")


def test_cognitive_cycle_is_coordinator_structure() -> None:
    """CognitiveCycle.run()はコーディネーターループであり、ビジネスロジックを含んではならない。

    run()がLLM呼び出し、ストア保存、アダプター呼び出しではなく、
    ステップとframe_builderに委譲することを確認する。
    """
    path = TARGET_FILES["cycle_service"]
    _skip_if_missing(path)
    tree = _parse(path)
    cls = _find_class(tree, "CognitiveCycle")
    assert cls is not None, "CognitiveCycle class not found"

    run_method = None
    for node in cls.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "run":
            run_method = node
            break

    if run_method is None:
        pytest.fail("CognitiveCycle has no run() method")

    method_text = ast.get_source_segment(path.read_text(encoding="utf-8"), run_method) or ""
    # Check the method calls step.run() and frame_builder.apply() — this is the coordinator pattern
    has_step_loop = "for step in " in method_text and ".run(" in method_text
    has_frame_builder = (
        "_frame_builder.apply(" in method_text or "frame_builder.apply(" in method_text
    )

    if not (has_step_loop and has_frame_builder):
        pytest.fail("CognitiveCycle.run() must delegate to step + FrameBuilder (coordinator)")


# ── 4. PipelineStep typed results ──────────────────────────────


def test_pipeline_step_returns_typed_result() -> None:
    """PipelineStep.run()の戻り値型はPipelineStepResultサブタイプでなければならない。"""
    path = TARGET_FILES["pipeline"]
    _skip_if_missing(path)
    tree = _parse(path)

    # Check the PipelineStep protocol has a return type annotation
    cls = _find_class(tree, "PipelineStep")
    if cls is None:
        # Could be a Protocol class
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and "PipelineStep" in node.name:
                cls = node
                break
    if cls is None:
        pytest.fail("PipelineStep class/protocol not found in pipeline.py")

    run_method = None
    for node in cls.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "run":
            run_method = node
            break

    assert run_method is not None, "PipelineStep must define run() method"

    # Check return type annotation exists
    returns = run_method.returns
    assert returns is not None, "PipelineStep.run() must have a return type annotation"

    return_type_str = ast.unparse(returns)
    assert "PipelineStepResult" in return_type_str or "ResultT" in return_type_str, (
        f"PipelineStep.run() return type must be a PipelineStepResult subtype,"
        f" got '{return_type_str}'"
    )


def test_pipeline_step_no_forbidden_imports() -> None:
    """PipelineStepの実装はアダプター、ランタイム、機能を直接呼び出してはならない。"""
    cognitive_dir = PROJECT_ROOT / "iris" / "cognitive"
    if not cognitive_dir.is_dir():
        pytest.skip("iris/cognitive/ does not exist yet")

    forbidden = {"iris.adapters", "iris.runtime", "iris.features"}
    violations: list[str] = []

    for filepath in sorted(cognitive_dir.rglob("*.py")):
        if "workspace/frame.py" in str(filepath) or "cycle/models.py" in str(filepath):
            continue
        try:
            tree = ast.parse(filepath.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for imp in _get_imports(tree):
            for f in forbidden:
                if imp.startswith(f):
                    rel = filepath.relative_to(PROJECT_ROOT).as_posix()
                    violations.append(f"  {rel}: imports '{imp}'")

    assert not violations, (
        "PipelineSteps in iris/cognitive/ must not import adapters/runtime/features:\n"
        + "\n".join(violations)
    )


@pytest.mark.parametrize(
    ("result_class", "expected_parent"),
    [
        ("PerceptionResult", "PipelineStepResult"),
        ("MemoryRetrievalResult", "PipelineStepResult"),
        ("AppraisalResult", "PipelineStepResult"),
        ("RelationshipResult", "PipelineStepResult"),
        ("MotivationResult", "PipelineStepResult"),
        ("PolicyResult", "PipelineStepResult"),
        ("ActionSelectionResult", "PipelineStepResult"),
    ],
)
def test_step_results_inherit_from_base(result_class: str, expected_parent: str) -> None:
    """各PipelineStepの結果型はPipelineStepResultを継承しなければならない。"""
    path = TARGET_FILES["cycle_models"]
    _skip_if_missing(path)
    tree = _parse(path)
    cls = _find_class(tree, result_class)
    if cls is None:
        pytest.fail(f"{result_class} not found in cycle/models.py")

    base_names = [ast.unparse(b) for b in cls.bases]
    assert expected_parent in base_names, (
        f"{result_class} must inherit from {expected_parent}, bases: {base_names}"
    )


# ── 5. PipelineStep frame immutability ─────────────────────────


def _collect_file_frame_mutation_violations(filepath: Path) -> list[str]:
    """Collect WorkspaceFrame direct mutation violations from a single cognitive file.

    Returns:
        Violation message list for this file.
    """
    violations: list[str] = []
    try:
        tree = ast.parse(filepath.read_text(encoding="utf-8"))
    except SyntaxError:
        return violations
    rel = filepath.relative_to(PROJECT_ROOT).as_posix()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            violations.extend(
                f"  {rel}:{node.lineno} mutates frame.{target.attr} directly"
                for target in node.targets
                if isinstance(target, ast.Attribute)
                and isinstance(target.value, ast.Name)
                and target.value.id == "frame"
            )
    return violations


def test_pipeline_step_does_not_mutate_frame() -> None:
    """PipelineStep.run()の実装はフレームをその場で変更してはならない。

    'frame'パラメータの属性をターゲットとするAssignノードをスキャンする。
    """
    cognitive_dir = PROJECT_ROOT / "iris" / "cognitive"
    if not cognitive_dir.is_dir():
        pytest.skip("iris/cognitive/ does not exist yet")

    violations: list[str] = []
    for filepath in sorted(cognitive_dir.rglob("*.py")):
        if (
            "workspace/frame.py" in str(filepath)
            or "cycle/frame_builder.py" in str(filepath)
            or "cycle/models.py" in str(filepath)
        ):
            continue
        violations.extend(_collect_file_frame_mutation_violations(filepath))

    assert not violations, (
        "PipelineSteps must not mutate WorkspaceFrame directly — use FrameBuilder:\n"
        + "\n".join(violations)
    )


# ── 6. IrisApp runtime flow ────────────────────────────────────


TARGET_APP_FILE: Path = PROJECT_ROOT / "iris" / "runtime" / "app.py"
TARGET_ACTIONS_FILE: Path = PROJECT_ROOT / "iris" / "contracts" / "actions.py"


def test_iris_app_checks_no_action_before_safety_gate() -> None:
    """IrisApp.process_observationはセーフティゲートを呼び出す前にis_no_actionをチェックしなければならない。"""
    if not TARGET_APP_FILE.is_file():
        pytest.skip("iris/runtime/app.py does not exist yet")

    text = TARGET_APP_FILE.read_text(encoding="utf-8")
    tree = ast.parse(text)

    cls = None
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "IrisApp":
            cls = node
            break
    assert cls is not None, "IrisApp class not found in app.py"

    method = None
    for node in cls.body:
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "process_observation"
        ):
            method = node
            break
    assert method is not None, "IrisApp.process_observation() not found"

    method_source = ast.get_source_segment(text, method) or ""

    assert "is_no_action" in method_source, (
        "process_observation() must check plan.is_no_action to shortcut no-action plans"
    )
    assert "check_plan" in method_source, (
        "process_observation() must call action_safety_gate.check_plan()"
    )
    assert "present" in method_source, "process_observation() must call presenter.present()"
    assert "check_output" in method_source, (
        "process_observation() must call output_safety_gate.check_output()"
    )


def test_iris_app_no_action_returns_presented_output_with_no_text() -> None:
    """IrisApp.process_observationはno-actionに対してPresentedOutput(text=None)を返さなければならない。"""
    if not TARGET_APP_FILE.is_file():
        pytest.skip("iris/runtime/app.py does not exist yet")

    text = TARGET_APP_FILE.read_text(encoding="utf-8")
    assert "PresentedOutput(text=None)" in text, (
        "no-action shortcut must return PresentedOutput(text=None)"
    )


# ── 7. ActionPlan.is_no_action / PresentedOutput.is_sendable ───


def test_action_plan_is_no_action_property() -> None:
    """ActionPlan.is_no_actionはturn_intentとshould_respondをチェックするプロパティでなければならない。"""
    if not TARGET_ACTIONS_FILE.is_file():
        pytest.skip("iris/contracts/actions.py does not exist yet")

    tree = ast.parse(TARGET_ACTIONS_FILE.read_text(encoding="utf-8"))
    cls = None
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "ActionPlan":
            cls = node
            break
    assert cls is not None, "ActionPlan class not found"

    found_is_no_action = False
    for node in cls.body:
        if isinstance(node, ast.FunctionDef) and node.name == "is_no_action":
            assert node.decorator_list, "is_no_action must be a @property"
            decorator_names = _get_decorator_names(node)
            assert "property" in decorator_names, "is_no_action must be a @property"
            found_is_no_action = True

    assert found_is_no_action, "ActionPlan.is_no_action property not found"


def test_presented_output_is_sendable_property() -> None:
    """PresentedOutput.is_sendableはtextがNoneでないことをチェックするプロパティでなければならない。"""
    if not TARGET_ACTIONS_FILE.is_file():
        pytest.skip("iris/contracts/actions.py does not exist yet")

    tree = ast.parse(TARGET_ACTIONS_FILE.read_text(encoding="utf-8"))
    cls = None
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "PresentedOutput":
            cls = node
            break
    assert cls is not None, "PresentedOutput class not found"

    found_is_sendable = False
    for node in cls.body:
        if isinstance(node, ast.FunctionDef) and node.name == "is_sendable":
            assert node.decorator_list, "is_sendable must be a @property"
            found_is_sendable = True

    assert found_is_sendable, "PresentedOutput.is_sendable property not found"


# ── 8. FeatureDefinition field completeness ─────────────────────


TARGET_FEATURE_DEF_FILE: Path = PROJECT_ROOT / "iris" / "features" / "definition.py"

REQUIRED_FEATURE_DEFINITION_FIELDS: set[str] = {
    "name",
    "cognitive_steps",
    "observation_sources",
    "learning_hooks",
    "background_jobs",
}


def test_feature_definition_has_all_required_fields() -> None:
    """FeatureDefinitionは5つすべての拡張ポイントフィールドを公開しなければならない。"""
    if not TARGET_FEATURE_DEF_FILE.is_file():
        pytest.skip("iris/features/definition.py does not exist yet")

    tree = ast.parse(TARGET_FEATURE_DEF_FILE.read_text(encoding="utf-8"))
    cls = None
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "FeatureDefinition":
            cls = node
            break
    assert cls is not None, "FeatureDefinition class not found"

    field_names: set[str] = set()
    for item in cls.body:
        if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
            field_names.add(item.target.id)

    missing = REQUIRED_FEATURE_DEFINITION_FIELDS - field_names
    assert not missing, f"FeatureDefinition missing required fields: {missing}"


# ── 9. PipelineStepResult subclasses frozen ─────────────────────


def test_all_pipeline_step_results_are_frozen_dataclass() -> None:
    """すべてのPipelineStepResultサブクラスはfrozen dataclassでなければならない。"""
    path = TARGET_FILES["cycle_models"]
    if not path.is_file():
        pytest.skip("cycle/models.py does not exist yet")

    tree = ast.parse(path.read_text(encoding="utf-8"))
    pipeline_result_classes: list[tuple[str, bool, bool]] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            bases = [ast.unparse(b) for b in node.bases]
            if "PipelineStepResult" in bases:
                is_frozen = _class_has_frozen_dataclass(node)
                is_dataclass = _class_has_dataclass(node)
                pipeline_result_classes.append((node.name, is_frozen, is_dataclass))

    violations = [
        f"  {name}: frozen={frozen}, dataclass={dc}"
        for name, frozen, dc in pipeline_result_classes
        if not frozen or not dc
    ]
    assert not violations, (
        "PipelineStepResult subclasses must be frozen dataclasses:\n" + "\n".join(violations)
    )
