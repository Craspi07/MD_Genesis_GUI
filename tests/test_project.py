from pathlib import Path

from app.project import Project, ModelType, InputMode, Engine


def test_round_trip(tmp_path: Path):
    project = Project(
        name="my_protein",
        directory="~/genesis_projects/my_protein",
        model_type=ModelType.HPS_CONDENSATE,
        input_mode=InputMode.SEQUENCE,
        sequence="MKTAYIAKQR",
    )
    project.parameters.n_steps = 500_000
    project.resources.engine = Engine.CGDYN
    project.resources.mpi_ranks = 8
    project.resources.omp_threads = 2

    project.save(str(tmp_path))
    loaded = Project.load(str(tmp_path))

    assert loaded.name == "my_protein"
    assert loaded.model_type == ModelType.HPS_CONDENSATE
    assert loaded.input_mode == InputMode.SEQUENCE
    assert loaded.sequence == "MKTAYIAKQR"
    assert loaded.parameters.n_steps == 500_000
    assert loaded.resources.engine == Engine.CGDYN
    assert loaded.resources.mpi_ranks == 8
    assert loaded.resources.omp_threads == 2


def test_defaults():
    project = Project(name="x", directory="~/genesis_projects/x")
    assert project.model_type == ModelType.AICG2P
    assert project.input_mode == InputMode.PDB
    assert project.resources.engine == Engine.ATDYN
    assert project.last_run_status == "not_started"
