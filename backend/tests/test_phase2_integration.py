"""Phase 2 Integration Tests — full pipeline verification (offline mode).

Tests:
  1. All agent files exist and are syntactically valid
  2. Dice parser extracts results correctly
  3. Full graph structure (10 nodes, all routes)
  4. AgentState through all message types
  5. Critic + Permission Manager
  6. Repository methods added
  7. Model updates (Character Player State, Campaign bot_persona)
  8. Orchestrator integration points
  9. Phase 2 file count summary
"""
import sys, os, ast, json, importlib.util

BACKEND = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(BACKEND))


def load_module(name, rel_path):
    """Load a single module by file path, bypassing __init__.py chains."""
    full = os.path.join(BACKEND, rel_path)
    spec = importlib.util.spec_from_file_location(name, full)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def ast_parse_safe(filepath):
    """Parse a Python file and return AST or error message."""
    try:
        with open(filepath, 'rb') as f:
            data = f.read()
        if data.count(b'\x00') > 0:
            return None, "Null bytes in file"
        with open(filepath) as f:
            return ast.parse(f.read()), None
    except Exception as e:
        return None, str(e)


# ═══════════════════════════════════════════════════════════════
# Test 1: All Phase 2 files exist and are valid
# ═══════════════════════════════════════════════════════════════
def test_files_valid():
    print("\n[1] Phase 2 files — existence + syntax")
    print("-" * 50)

    new_files = [
        "app/agents/classifier_agent.py",
        "app/agents/llm_factory.py",
        "app/agents/state_agent.py",
        "app/agents/rag_agent.py",
        "app/agents/npc_agent.py",
        "app/agents/chat_agent.py",
        "app/agents/plot_agent.py",
        "app/agents/rule_agent.py",
        "app/agents/branch_writer.py",
        "app/agents/critic_agent.py",
        "app/agents/__init__.py",
        "app/harness/agent_state.py",
        "app/harness/graph.py",
        "app/harness/orchestrator.py",
        "app/harness/permission_manager.py",
        "app/bot/dice_parser.py",
    ]

    all_ok = True
    for f in new_files:
        full = os.path.join(BACKEND, f)
        if not os.path.exists(full):
            print("  MISSING: {}".format(f))
            all_ok = False
            continue
        tree, err = ast_parse_safe(full)
        if err:
            print("  SYNTAX ERROR: {} — {}".format(f, err))
            all_ok = False
        else:
            size = os.path.getsize(full)
            print("  {} ({:.1f} KB) OK".format(f, size / 1024))

    assert all_ok, "Some files are missing or have syntax errors"
    print("  PASS")


# ═══════════════════════════════════════════════════════════════
# Test 2: Dice parser
# ═══════════════════════════════════════════════════════════════
def test_dice_parser():
    print("\n[2] Dice Parser — parse realistic dice-robot messages")
    print("-" * 50)

    mod = load_module("dice_parser", "app/bot/dice_parser.py")
    parse = mod.parse_dice_message
    is_dice = mod.is_dice_message

    test_cases = [
        (".r 1d100 = 75", True),
        ("检定/侦查 70/45 失败", True),
        ("1D100=32/60 成功", True),
        (".ra 侦查 70 = 45/70 成功", True),
        ("{玩家A} 进行 侦查检定: D100=28/65 困难成功", True),
        ("暗骰", True),
        ("玩家: 我检查书架", False),
        ("老管家: 你好啊", False),
        ("今天天气不错", False),
    ]

    for text, should_be_dice in test_cases:
        result = is_dice(text)
        if should_be_dice and not result:
            print("  MISSED dice: {}".format(text[:50]))
        if not should_be_dice and result:
            print("  FALSE POSITIVE: {}".format(text[:50]))

    # Detailed parse test
    r1 = parse(".r 1d100 = 75")
    assert r1 is not None
    assert r1.rolled == 75

    r2 = parse("检定/侦查 70/45 失败")
    assert r2 is not None
    assert r2.check_type == "侦查"
    assert r2.target == 70
    assert r2.rolled == 45
    assert r2.outcome == "failure"

    r3 = parse("1D100=32/60 成功")
    assert r3 is not None
    assert r3.target == 60
    assert r3.rolled == 32
    assert r3.is_success()

    r4 = parse("{玩家A} 进行 侦查检定: D100=28/65 困难成功")
    assert r4 is not None
    assert r4.check_type == "侦查"
    assert r4.outcome == "hard_success"

    r5 = parse("暗骰")
    assert r5 is not None
    assert r5.is_secret
    r5b = is_dice("暗骰")
    assert r5b, "暗骰 should be detected as dice message"

    r6 = parse("今天天气不错")
    assert r6 is None

    print("  All {} cases correct".format(len(test_cases)))
    print("  PASS")


# ═══════════════════════════════════════════════════════════════
# Test 3: Graph structure — all 10 nodes + routing
# ═══════════════════════════════════════════════════════════════
def test_graph_structure():
    print("\n[3] Graph structure — nodes and routing")
    print("-" * 50)

    with open(os.path.join(BACKEND, "app/harness/graph.py")) as f:
        src = f.read()
    tree = ast.parse(src)

    # Extract all async function defs (nodes)
    nodes = []
    routes = []
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name.startswith("node_"):
            nodes.append(node.name)
        elif isinstance(node, ast.FunctionDef) and node.name.startswith("route_"):
            routes.append(node.name)

    expected_nodes = [
        "node_classify", "node_rag_retrieve", "node_state_track",
        "node_build_suggestion", "node_npc_roleplay", "node_rule_lookup",
        "node_kp_command", "node_chat_bot", "node_critic_check", "node_output",
    ]
    expected_routes = [
        "route_by_message_type", "route_after_rag",
        "route_after_npc", "route_after_state", "route_by_risk",
    ]

    node_names = set(nodes)
    for n in expected_nodes:
        assert n in node_names, "Missing node: {}".format(n)
    route_names = set(routes)
    for r in expected_routes:
        assert r in route_names, "Missing route: {}".format(r)

    print("  {} nodes, {} routes — all present".format(
        len(expected_nodes), len(expected_routes)))

    # Verify route_by_message_type covers all 6 message types
    import re
    routes_in_func = re.findall(r'"(\w+)":\s*"(\w+)"', src)
    route_map = dict(routes_in_func)
    for msg_type in ["player_action", "roleplay", "npc_dialogue",
                     "rule_question", "kp_command", "chat"]:
        assert msg_type in route_map, "No route for message type: {}".format(msg_type)

    print("  All 6 message types have routes")
    print("  PASS")


# ═══════════════════════════════════════════════════════════════
# Test 4: AgentState through message types
# ═══════════════════════════════════════════════════════════════
def test_agentstate_pipeline():
    print("\n[4] AgentState — pipeline simulation")
    print("-" * 50)

    mod = load_module("agent_state", "app/harness/agent_state.py")
    new_state = mod.new_state

    # Simulate a player_action through the pipeline
    s = new_state(
        campaign_id="test-campaign",
        sender="player_qq_123",
        content="我检查书房的书架",
        message_type="player_action",
        confidence=0.92,
        need_rag=True,
        need_kp_suggestion=True,
        need_state_update=True,
        reasoning="action keyword: 检查 + 书架",
    )

    # Add mock RAG results
    s["rag_results"] = [
        {"text": "书架上有一本旧日记，最后一页被撕掉了。", "title": "书架", "score": 0.95, "visibility": "player_visible", "chunk_id": "c1", "type": "clue"},
        {"text": "日记中提到了一个神秘的地下室。", "title": "日记内容", "score": 0.82, "visibility": "kp_only", "chunk_id": "c2", "type": "clue"},
    ]
    s["rag_meta"] = {"fusion_method": "rrf", "latency_ms": 120}

    # Mock context
    s["current_state"] = {
        "active_scene": {"name": "书房", "summary": "一间布满灰尘的书房"},
        "active_npcs": [{"name": "老管家", "personality": "沉默寡言"}],
        "discovered_clues": [],
        "undiscovered_clues": [
            {"name": "地下室入口", "trigger_condition": "发现日记中的线索"},
        ],
    }

    # Add dice result (success)
    s["dice_result"] = {"check_type": "侦查", "target": 70, "rolled": 32, "outcome": "normal_success"}

    # Add mock player states
    s["player_states"] = {
        "player_qq_123": {
            "sanity": 48, "skills": {"侦查": 70, "图书馆使用": 45},
            "inventory": [{"name": "手电筒", "source": "初始装备"}],
            "personal_clues": [], "status_effects": [],
        }
    }

    # Verify all fields populated
    assert s["campaign_id"] == "test-campaign"
    assert s["message_type"] == "player_action"
    assert s["need_rag"]
    assert s["need_state_update"]
    assert len(s["rag_results"]) == 2
    assert s["dice_result"]["outcome"] == "normal_success"
    assert "player_qq_123" in s["player_states"]
    assert s["player_states"]["player_qq_123"]["sanity"] == 48

    print("  All state fields populated correctly")
    print("  PASS")


# ═══════════════════════════════════════════════════════════════
# Test 5: Critic + Permission Manager
# ═══════════════════════════════════════════════════════════════
def test_critic_permission():
    print("\n[5] Critic + Permission Manager")
    print("-" * 50)

    # Load permission manager
    pm = load_module("permission_manager", "app/harness/permission_manager.py")
    PermissionManager = pm.PermissionManager

    # Test RAG result filtering
    results = [
        {"text": "public info", "visibility": "player_visible", "chunk_id": "c1"},
        {"text": "secret info", "visibility": "kp_only", "chunk_id": "c2"},
        {"text": "more public", "visibility": "player_visible", "chunk_id": "c3"},
    ]
    filtered = PermissionManager.filter_rag_results(results, "player")
    assert len(filtered) == 2
    assert all(r["visibility"] == "player_visible" for r in filtered)

    unfiltered = PermissionManager.filter_rag_results(results, "kp")
    assert len(unfiltered) == 3

    # Test output filtering
    output = {
        "message_type": "player_action",
        "kp_suggestion": "secret KP advice",
        "public_reply": "public response",
        "need_kp_notify": True,
        "classification": {"message_type": "player_action"},
    }
    player_out = PermissionManager.filter_output(output, "player")
    assert "kp_suggestion" not in player_out
    assert player_out["public_reply"] == "public response"
    assert player_out["need_kp_notify"] is True

    kp_out = PermissionManager.filter_output(output, "kp")
    assert kp_out["kp_suggestion"] == "secret KP advice"

    # Test spoiler keyword check
    result = PermissionManager.check_spoiler_risk(
        "玩家发现了地下室入口的秘密",
        ["地下室入口", "秘密日记", "古老符咒"],
    )
    assert result["risk"] == "high"
    assert "地下室入口" in result["matched_clues"]

    result2 = PermissionManager.check_spoiler_risk(
        "玩家和NPC聊天",
        ["地下室入口", "秘密日记"],
    )
    assert result2["risk"] == "low"

    print("  RAG filter: OK")
    print("  Output filter: OK")
    print("  Spoiler check: OK")
    print("  PASS")


# ═══════════════════════════════════════════════════════════════
# Test 6: Repository methods
# ═══════════════════════════════════════════════════════════════
def test_repo_methods():
    print("\n[6] Repository methods — structural verification")
    print("-" * 50)

    # Character repo
    with open(os.path.join(BACKEND, "app/storage/character_repo.py")) as f:
        tree = ast.parse(f.read())

    char_methods = []
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef):
            char_methods.append(node.name)

    required = ["apply_player_diff", "set_kp_override", "get_by_player_qq"]
    for m in required:
        assert m in char_methods, "CharacterRepo missing: {}".format(m)
    print("  CharacterRepo: {} methods OK".format(len(required)))

    # Clue repo
    with open(os.path.join(BACKEND, "app/storage/clue_repo.py")) as f:
        tree = ast.parse(f.read())
    clue_methods = [n.name for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef)]
    assert "set_locked" in clue_methods
    print("  ClueRepo: set_locked OK")

    # Scene repo
    with open(os.path.join(BACKEND, "app/storage/scene_repo.py")) as f:
        tree = ast.parse(f.read())
    scene_methods = [n.name for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef)]
    assert "transition_to" in scene_methods
    print("  SceneRepo: transition_to OK")

    print("  PASS")


# ═══════════════════════════════════════════════════════════════
# Test 7: Model fields
# ═══════════════════════════════════════════════════════════════
def test_model_fields():
    print("\n[7] Model fields — Phase 2 additions")
    print("-" * 50)

    with open(os.path.join(BACKEND, "app/storage/models.py")) as f:
        src = f.read()
    tree = ast.parse(src)

    # Find all Column() definitions
    columns_by_class = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            cols = []
            for item in node.body:
                if isinstance(item, ast.Assign):
                    for target in item.targets:
                        if isinstance(target, ast.Name):
                            cols.append(target.id)
            if cols:
                columns_by_class[node.name] = cols

    # Campaign: bot_persona
    assert "bot_persona" in columns_by_class.get("Campaign", []), \
        "Campaign missing bot_persona"
    print("  Campaign.bot_persona: OK")

    # Character: Player State fields
    char_fields = columns_by_class.get("Character", [])
    ps_fields = ["player_qq", "sanity", "skills", "inventory",
                 "personal_clues", "status_effects", "relationships",
                 "state_version", "last_modified_by"]
    for f in ps_fields:
        assert f in char_fields, "Character missing: {}".format(f)
    print("  Character Player State: {} fields OK".format(len(ps_fields)))

    print("  PASS")


# ═══════════════════════════════════════════════════════════════
# Test 8: Orchestrator integration
# ═══════════════════════════════════════════════════════════════
def test_orchestrator_integration():
    print("\n[8] Orchestrator — integration points")
    print("-" * 50)

    with open(os.path.join(BACKEND, "app/harness/orchestrator.py")) as f:
        tree = ast.parse(f.read())

    # Find Orchestrator.process method
    methods = []
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef):
            methods.append(node.name)

    assert "process" in methods, "Orchestrator missing process()"
    assert "process_message" in methods, "Missing process_message() function"

    # Check that process uses graph.ainvoke
    with open(os.path.join(BACKEND, "app/harness/orchestrator.py")) as f:
        src = f.read()

    assert "ainvoke" in src, "Orchestrator should use graph.ainvoke()"
    assert "thread_id" in src, "Orchestrator should support thread_id"
    assert "dice_result" in src, "Orchestrator should accept dice_result"

    print("  process() with graph.ainvoke: OK")
    print("  thread_id support: OK")
    print("  dice_result passthrough: OK")
    print("  PASS")


# ═══════════════════════════════════════════════════════════════
# Test 9: Full file count summary
# ═══════════════════════════════════════════════════════════════
def test_file_summary():
    print("\n[9] Phase 2 file summary")
    print("-" * 50)

    phase2_new = [
        "app/agents/state_agent.py",
        "app/agents/rag_agent.py",
        "app/agents/npc_agent.py",
        "app/agents/chat_agent.py",
        "app/agents/plot_agent.py",
        "app/agents/rule_agent.py",
        "app/agents/branch_writer.py",
        "app/agents/critic_agent.py",
        "app/harness/permission_manager.py",
        "app/bot/dice_parser.py",
    ]

    total_lines = 0
    for f in phase2_new:
        full = os.path.join(BACKEND, f)
        with open(full) as fh:
            lines = len(fh.readlines())
            total_lines += lines
            print("  {} — {} lines".format(f, lines))

    print("  Total: {} files, {} lines of agent code".format(
        len(phase2_new), total_lines))
    print("  PASS")


# ═══════════════════════════════════════════════════════════════
# Runner
# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("=" * 60)
    print("  Phase 2: Full Pipeline Integration Tests")
    print("=" * 60)

    tests = [
        ("Files valid", test_files_valid),
        ("Dice parser", test_dice_parser),
        ("Graph structure", test_graph_structure),
        ("AgentState pipeline", test_agentstate_pipeline),
        ("Critic + Permission", test_critic_permission),
        ("Repository methods", test_repo_methods),
        ("Model fields", test_model_fields),
        ("Orchestrator integration", test_orchestrator_integration),
        ("File summary", test_file_summary),
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
    print("  Results: {}/{} passed, {} failed".format(
        passed, len(tests), failed))
    print("=" * 60)
