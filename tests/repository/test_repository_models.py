import json
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.repository.models import RepositorySnapshot


def test_valid_snapshot_serializes_to_json():
    snapshot = RepositorySnapshot(
        source_type="local",
        repository_name="sample",
        source_reference="/source/sample",
        workspace_id=uuid4(),
        files=[],
        total_files=0,
        total_size_bytes=0,
    )
    assert json.loads(snapshot.model_dump_json())["source_type"] == "local"


def test_invalid_source_type_is_rejected():
    with pytest.raises(ValidationError):
        RepositorySnapshot(
            source_type="gitlab",
            repository_name="sample",
            source_reference="/source/sample",
            workspace_id=uuid4(),
            total_files=0,
            total_size_bytes=0,
        )
