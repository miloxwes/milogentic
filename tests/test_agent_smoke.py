from agentic_app.agent import build_agent


def test_agent_runs_to_final_text(tmp_path):
    db_path = tmp_path / "memory.db"
    agent = build_agent(db_path=str(db_path))
    res = agent.run("s1", "Book me a flight SFO to JFK under $500.")
    assert isinstance(res.final_text, str)
    assert len(res.final_text) > 0
