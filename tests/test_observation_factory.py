from aether.planning.observation import ObservationFactory, CharacterBudget

def test_observation_under_budget():
    budget = CharacterBudget(max_chars=100)
    factory = ObservationFactory(budget=budget)
    
    payload = "Short payload"
    obs = factory.create(plan_id="p1", step_id="s1", action_taken="test", payload=payload)
    
    assert obs.result == "Short payload"
    assert not obs.metadata.get("truncated", False)

def test_observation_over_budget():
    budget = CharacterBudget(max_chars=10)
    factory = ObservationFactory(budget=budget)
    
    payload = "This is a very long payload that should be truncated"
    obs = factory.create(plan_id="p1", step_id="s1", action_taken="test", payload=payload)
    
    assert len(obs.result) == 10
    assert obs.result == "This is a "
    assert obs.metadata.get("truncated") is True
    assert obs.metadata.get("original_size") == len(payload)

def test_observation_over_budget_json():
    budget = CharacterBudget(max_chars=10)
    factory = ObservationFactory(budget=budget)
    
    payload = {"key": "very long value that will exceed"}
    obs = factory.create(plan_id="p1", step_id="s1", action_taken="test", payload=payload)
    
    assert isinstance(obs.result, dict)
    assert obs.result["error"] == "payload_truncated"
    assert obs.result["reason"] == "character_budget_exceeded"
    assert "original_size" in obs.result
    
    assert obs.metadata.get("truncated") is True
    assert obs.metadata.get("original_size") > 10
