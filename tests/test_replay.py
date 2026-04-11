"""Tests for replay engine."""

import tempfile
from pathlib import Path
from agentguard.replay import ReplayEngine, ReplayCase


def test_save_and_load_baseline():
    """Baselines can be saved and loaded."""
    with tempfile.TemporaryDirectory() as tmpdir:
        engine = ReplayEngine(baselines_dir=str(Path(tmpdir) / "baselines"))
        
        case = engine.save_baseline(
            name="test-case-1",
            input_data={"topic": "AI"},
            output_data={"articles": [{"title": "A"}, {"title": "B"}]},
            rules=[{"type": "min_count", "target": "articles", "value": 2}],
        )
        
        loaded = engine.load_baseline("test-case-1")
        assert loaded is not None
        assert loaded.name == "test-case-1"
        assert loaded.input_data == {"topic": "AI"}
        assert len(loaded.rules) == 1


def test_list_baselines():
    """list_baselines returns all saved case names."""
    with tempfile.TemporaryDirectory() as tmpdir:
        engine = ReplayEngine(baselines_dir=str(Path(tmpdir) / "baselines"))
        engine.save_baseline("case-a", input_data={}, output_data={})
        engine.save_baseline("case-b", input_data={}, output_data={})
        
        names = engine.list_baselines()
        assert set(names) == {"case-a", "case-b"}


def test_compare_improved():
    """Compare detects improvement when candidate passes more rules."""
    with tempfile.TemporaryDirectory() as tmpdir:
        engine = ReplayEngine(baselines_dir=str(Path(tmpdir) / "baselines"))
        
        # Baseline has 2 articles (fails min_count=3)
        engine.save_baseline(
            name="test",
            input_data={"topic": "AI"},
            output_data={"articles": [{"title": "A"}, {"title": "B"}]},
            rules=[{"type": "min_count", "target": "articles", "value": 3}],
        )
        
        # Candidate has 5 articles (passes)
        candidate = {"articles": [{"title": c} for c in "ABCDE"]}
        result = engine.compare("test", candidate)
        
        assert result.verdict == "improved"


def test_compare_regressed():
    """Compare detects regression when candidate passes fewer rules."""
    with tempfile.TemporaryDirectory() as tmpdir:
        engine = ReplayEngine(baselines_dir=str(Path(tmpdir) / "baselines"))
        
        # Baseline has 5 articles (passes min_count=3)
        engine.save_baseline(
            name="test",
            input_data={},
            output_data={"articles": [{"title": c} for c in "ABCDE"]},
            rules=[{"type": "min_count", "target": "articles", "value": 3}],
        )
        
        # Candidate has 1 article (fails)
        result = engine.compare("test", {"articles": [{"title": "A"}]})
        assert result.verdict == "regressed"


def test_run_regression():
    """run_regression tests all baselines with an agent function."""
    with tempfile.TemporaryDirectory() as tmpdir:
        engine = ReplayEngine(baselines_dir=str(Path(tmpdir) / "baselines"))
        
        engine.save_baseline("case-1", input_data={"n": 5}, output_data={"items": list(range(5))},
                            rules=[{"type": "min_count", "target": "items", "value": 3}])
        engine.save_baseline("case-2", input_data={"n": 2}, output_data={"items": list(range(2))},
                            rules=[{"type": "min_count", "target": "items", "value": 3}])
        
        # Agent that generates n items
        def agent(input_data):
            n = input_data.get("n", 0)
            return {"items": list(range(n))}
        
        results = engine.run_regression(agent)
        assert len(results) == 2
