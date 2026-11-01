from types import SimpleNamespace

import httpx
import pytest
from openai import APIConnectionError

from app.evaluation.quality import quality_gate, validation_gate
from app.services.embedding_service import EmbeddingServiceError, OpenAIEmbeddingService


def test_advisory_and_hard_gate_outcomes():
    assert quality_gate("fixture", True, hard=True, category="invalid").status == "passed"
    assert quality_gate("fixture", False, hard=False, category="weak_evidence").status == "failed"
    with pytest.raises(ValueError, match="rejected"):
        quality_gate("fixture", False, hard=True, category="weak_evidence")
    with pytest.raises(ValueError, match="original"):
        with validation_gate("fixture"):
            raise ValueError("original contract")


def test_embedding_retry_limit_and_permanent_classification(monkeypatch):
    from app.services import embedding_service
    monkeypatch.setattr(embedding_service.time, "sleep", lambda seconds: None)
    provider = OpenAIEmbeddingService("synthetic-key", model="synthetic", max_retries=2)
    calls = []
    def transient(**kwargs):
        calls.append(1)
        raise APIConnectionError(request=httpx.Request("POST", "https://example.invalid"))
    provider._client = SimpleNamespace(embeddings=SimpleNamespace(create=transient))
    with pytest.raises(EmbeddingServiceError):
        provider.embed(["synthetic content"])
    assert len(calls) == 3
    calls.clear()
    def permanent(**kwargs):
        calls.append(1)
        raise ValueError("bad provider configuration")
    provider._client = SimpleNamespace(embeddings=SimpleNamespace(create=permanent))
    with pytest.raises(EmbeddingServiceError):
        provider.embed(["synthetic content"])
    assert len(calls) == 1


@pytest.mark.parametrize("maximum_nodes", [1, 5, 30])
def test_dependency_diagram_respects_node_budget(maximum_nodes):
    from tests.repository.visualization.test_milestone3_visualization import analysis_fixture
    from app.repository.analysis.models import DependencyFinding
    from app.repository.visualization.diagram_generator import DiagramGenerator
    from app.repository.visualization.diagram_validator import DiagramValidator
    analysis = analysis_fixture()
    analysis.dependencies = [
        DependencyFinding(source=f"source{index}", target=f"target{index}",
                          dependency_type="imports", resolved=True,
                          evidence_references=["E0002"])
        for index in range(40)
    ]
    diagram = DiagramGenerator(maximum_nodes=maximum_nodes)._dependencies(analysis)
    assert len(diagram.nodes) <= maximum_nodes
    assert len(diagram.relationships) == maximum_nodes // 2
    assert DiagramValidator(maximum_nodes=maximum_nodes).validate(diagram, analysis).valid
    assert diagram.generation_warnings


@pytest.mark.parametrize("hard", [False, True])
def test_visualizer_preserves_invalid_diagram_policy(monkeypatch, hard):
    from tests.repository.visualization.test_milestone3_visualization import analysis_fixture
    from app.config.settings import settings
    from app.repository.visualization.architecture_visualizer import ArchitectureVisualizer
    from app.repository.visualization.diagram_generator import DiagramGenerator
    from app.observability.context import bind_context
    from app.observability.metrics import operational_store
    from app.observability.models import QualityObservation
    analysis = analysis_fixture()
    diagram = DiagramGenerator()._dependencies(analysis)
    diagram.mermaid_source = ""
    renderer = SimpleNamespace(is_available=lambda: False)
    visualizer = ArchitectureVisualizer(
        diagram_generator=SimpleNamespace(generate=lambda analysis: [diagram]),
        diagram_renderer=renderer,
    )
    monkeypatch.setattr(settings, "diagram_require_valid", hard)
    with bind_context(owner_id=f"quality-policy-{hard}"):
        if hard:
            with pytest.raises(ValueError, match="rejected"):
                visualizer.visualize(analysis)
        else:
            result = visualizer.visualize(analysis)
            assert any("failed structural validation" in warning for warning in result.visualization_warnings)
    failure = [
        row.summary for row in operational_store.records(f"quality-policy-{hard}")
        if isinstance(row, QualityObservation) and row.summary.status == "failed"
    ][-1]
    assert failure.gate == "diagram.validity"
    assert failure.category == "invalid_diagram"
    assert failure.hard == hard
