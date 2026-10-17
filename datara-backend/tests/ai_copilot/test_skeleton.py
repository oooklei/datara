from pathlib import Path


def test_ai_copilot_module_exposes_a_datara_adapter():
    from ai_copilot.adapter import AdapterContext, CopilotAdapter

    assert callable(CopilotAdapter)
    assert callable(CopilotAdapter.generate_sql)
    assert callable(AdapterContext)


def test_chromadb_path_is_reserved_for_runtime_data_only():
    data_dir = Path(__file__).resolve().parents[2] / "data" / "ai_copilot" / "chromadb"

    assert data_dir.is_dir()
    assert (data_dir / ".gitkeep").is_file()
    assert {path.name for path in data_dir.iterdir()} <= {".gitkeep", ".gitignore"}
