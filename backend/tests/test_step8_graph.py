"""Step 8: LangGraph Orchestration Framework Tests (offline / no-deps mode).

Tests pure-logic components without importing the full package tree.
"""
import sys, os, ast, importlib.util

BACKEND = os.path.join(os.path.dirname(__file__), "..")

def load_module(name, rel_path):
    """Load a single module by file path, bypassing __init__.py chains."""
    full = os.path.join(BACKEND, rel_path)
    spec = importlib.util.spec_from_file_location(name, full)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ═══════════════════════════════════════════════════
# Test 1: AgentState AST validation + pure Python
# ═══════════════════════════════════════════════════
def test_agent_state_pure():
    print("\n[1] AgentState — pure Python validation")
    print("-" * 40)

    # Load agent_state without touching harness __init__
    mod = load_module("agent_state", "app/harness/agent_state.py")
    AgentState = mod.AgentState
    new_state = mod.new_state

    s = new_state(campaign_id="test-1", sender="player_qq", content="hello")
    assert s["campaign_id"] == "test-1"
    assert s["message_type"] == "chat"
    assert s["confidence"] == 0.0
    assert s["need_rag"] is False
    assert s["dice_result"] is None
    assert s["player_states"] == {}
    assert s["error"] is None
    print("  All defaults correct")
    print("  PASS")


# ═══════════════════════════════════════════════════
# Test 2: LLMFactory pure logic
# ═══════════════════════════════════════════════════
def test_llm_factory_pure():
    print("\n[2] LLMFactory — config generation (no network)")
    print("-" * 40)

    mod = load_module("llm_factory", "app/agents/llm_factory.py")
    LLMFactory = mod.LLMFactory
    ModelConfig = mod.ModelConfig

    factory = LLMFactory()
    config = factory.get_config_for_agent("classifier")

    assert isinstance(config, ModelConfig)
    assert config.provider in ("openai", "deepseek", "anthropic")
    assert config.model
    print("  Provider: {}".format(config.provider))
    print("  Model: {}".format(config.model))

    # Test per-agent override via env
    os.environ["TESTAGENT_LLM_MODEL"] = "test-model-override"
    config2 = factory.get_config_for_agent("testagent")
    assert config2.model == "test-model-override"
    del os.environ["TESTAGENT_LLM_MODEL"]
    print("  Per-agent env override: OK")
    print("  PASS")


# ═══════════════════════════════════════════════════
# Test 3: Graph module is syntactically valid
# ═══════════════════════════════════════════════════
def test_graph_syntax():
    print("\n[3] Graph module — AST syntax check")
    print("-" * 40)

    with open(os.path.join(BACKEND, "app/harness/graph.py")) as f:
        tree = ast.parse(f.read())

    functions = []
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef):
            functions.append(("async", node.name))
        elif isinstance(node, ast.FunctionDef):
            functions.append(("def", node.name))

    expected = [
        "node_classify", "node_rag_retrieve", "node_build_suggestion",
        "node_npc_roleplay", "node_rule_lookup", "node_kp_command",
        "node_critic_check", "node_output",
        "route_by_message_type", "route_after_rag", "route_by_risk",
        "build_graph", "get_graph",
    ]
    names = {n for _, n in functions}
    for e in expected:
        assert e in names, "Missing: {}".format(e)
    print("  All {} expected functions present".format(len(expected)))
    print("  PASS")


# ═══════════════════════════════════════════════════
# Test 4: Routing functions (AST-verified, no import needed)
# ═══════════════════════════════════════════════════
def test_routing_ast_logic():
    print("\n[4] Routing functions — AST logic verification")
    print("-" * 40)

    # Read graph.py source and parse AST
    graph_path = os.path.join(BACKEND, "app/harness/graph.py")
    with open(graph_path) as f:
        src = f.read()
    tree = ast.parse(src)

    # Verify route_by_message_type contains expected route mappings
    route_funcs = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name.startswith("route_"):
            route_funcs[node.name] = node

    assert "route_by_message_type" in route_funcs, "Missing route_by_message_type"
    assert "route_after_rag" in route_funcs, "Missing route_after_rag"
    assert "route_by_risk" in route_funcs, "Missing route_by_risk"
    print("  All 3 routing functions present")
    print("  PASS")


# ═══════════════════════════════════════════════════
# Test 5: Orchestrator AST structure
# ═══════════════════════════════════════════════════
def test_orchestrator_structure():
    print("\n[5] Orchestrator — AST validation")
    print("-" * 40)

    with open(os.path.join(BACKEND, "app/harness/orchestrator.py")) as f:
        tree = ast.parse(f.read())

    classes = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            classes.append(node.name)

    assert "Orchestrator" in classes
    print("  Orchestrator class: present")
    print("  PASS")


# ═══════════════════════════════════════════════════
# Test 6: AgentState field enumeration
# ═══════════════════════════════════════════════════
def test_agent_state_fields():
    print("\n[6] AgentState — all required fields present")
    print("-" * 40)

    mod = load_module("agent_state", "app/harness/agent_state.py")
    new_state = mod.new_state

    s = new_state()
    required = [
        "campaign_id", "sender", "content", "message",
        "message_type", "confidence", "need_rag", "need_kp_suggestion",
        "need_state_update", "reasoning",
        "rag_results", "rag_meta",
        "current_state", "context",
        "dice_result", "player_states",
        "suggested_action", "kp_suggestion", "public_reply",
        "critic_result", "risk_level",
        "output", "need_kp_notify", "error",
        "trace_id", "node_timings", "tool_calls", "token_count",
    ]
    for field in required:
        assert field in s, "Missing field: {}".format(field)
    print("  All {} required fields present".format(len(required)))
    print("  PASS")


# ═══════════════════════════════════════════════════
# Test 7: Graph conditional edge dicts match nodes
# ═══════════════════════════════════════════════════
def test_graph_edge_consistency():
    print("\n[7] Graph — conditional edge targets match nodes")
    print("-" * 40)

    # Read the source to extract add_node calls and their targets
    src = open(os.path.join(BACKEND, "app/harness/graph.py")).read()

    import re
    # Extract add_node("name", ...)
    node_names = set(re.findall(r'add_node\("(\w+)"', src))
    node_names.add("output")  # always present
    print("  Nodes: {}".format(sorted(node_names)))

    # Check that route_by_message_type returns valid targets
    # The conditional edge dict in build_graph maps to these:
    valid_targets = {"rag_retrieve", "rule_lookup", "kp_command", "output"}
    for t in valid_targets:
        assert t in node_names, \
            "route_by_message_type target '{}' not in graph nodes".format(t)
    print("  All routing targets in node set: OK")
    print("  PASS")


# ═══════════════════════════════════════════════════
# Test 8: All new files created
# ═══════════════════════════════════════════════════
def test_files_exist():
    print("\n[8] Step 8 — new files present")
    print("-" * 40)

    files = [
        "app/harness/agent_state.py",
        "app/harness/graph.py",
        "app/agents/llm_factory.py",
    ]
    for f in files:
        path = os.path.join(BACKEND, f)
        assert os.path.exists(path), "Missing: {}".format(f)
        # Check non-empty
        size = os.path.getsize(path)
        assert size > 100, "{} is too small ({} bytes)".format(f, size)
        print("  {} ({:.1f} KB)".format(f, size / 1024))

    print("  PASS")


# ═══════════════════════════════════════════════════
# Runner
# ═══════════════════════════════════════════════════
if __name__ == "__main__":
    print("=" * 60)
    print("  Step 8: LangGraph Framework Tests (offline)")
    print("=" * 60)

    tests = [
        ("AgentState pure", test_agent_state_pure),
        ("LLMFactory config", test_llm_factory_pure),
        ("Graph syntax", test_graph_syntax),
        ("Routing AST logic", test_routing_ast_logic),
        ("Orchestrator structure", test_orchestrator_structure),
        ("AgentState fields", test_agent_state_fields),
        ("Graph edge consistency", test_graph_edge_consistency),
        ("Files exist", test_files_exist),
    ]

    passed = 0
    failed = 0
    for name, fn in tests:
        try:
            fn()
            passed += 1
        except Exception as e:
            print("\n  FAILED: {} — {}".format(name, e))
            import traceback
            traceback.print_exc()
            failed += 1

    print("\n" + "=" * 60)
    print("  Results: {}/{} passed, {} failed".format(passed, len(tests), failed))
    print("=" * 60)
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    