import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["DD_DISABLE_LLM"] = "1"          # tests never call a real model
os.environ.pop("DD_LLM_COPY", None)

from dissdisc import service  # noqa: E402
from dissdisc.config import load_pack, load_survey_config  # noqa: E402
from dissdisc.curriculum.review import confirm_curriculum  # noqa: E402

SAMPLE = ROOT / "sample_data" / "economics_programme_handbook.txt"


@pytest.fixture(scope="session")
def cfg():
    return load_survey_config()


@pytest.fixture(scope="session")
def pack():
    return load_pack("economics")


@pytest.fixture(scope="session")
def sample_text():
    return SAMPLE.read_text(encoding="utf-8")


@pytest.fixture
def state():
    return service.new_session("economics", seed=123)


@pytest.fixture
def state_with_syllabus():
    st = service.new_session("economics", seed=123)
    service.load_sample_curriculum(st)
    confirm_curriculum(st)
    return st
