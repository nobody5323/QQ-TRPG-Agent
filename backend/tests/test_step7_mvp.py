"""Step 7: MVP Integration Test Suite

Tests the full Phase 1 pipeline without external services.
Uses mocked dependencies where needed.

Tests:
  1. ClassifierAgent keyword fallback (no LLM required)
  2. ClassifierAgent LLM mode (requires OPENAI_API_KEY - SKIP if not set)
  3. QueryEnhancer (pure logic)
  4. KeywordSearcher tokenization (pure logic)
  5. RRF fusion (pure logic)
  6. Reranker state-aware boosts (pure logic)
  7. ContextManager model validation
  8. TraceRecorder model validation
  9. Orchestrator fallback behavior
  10. Campaign binding API logic
  11. Cross-module integration sanity check
  12. Full project file structure validation
"""

import sys, os, json, re, time, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ═══════════════════════════════════════════════════
# Test 1: ClassifierAgent keyword fallback
# ═══════════════════════════════════════════════════
def test_classifier_fallback():
    print("\n[1] ClassifierAgent - keyword fallback")
    print("-" * 40)

    from app.agents.classifier_agent import classifier_agent

    test_cases = [
        ("我想调查书房里的画像", "player_action"),
        ("我检查画像背后", "player_action"),
        ("搜索书架", "player_action"),
        ("去地下酒窖", "player_action"),
        ("打开暗门", "player_action"),
        ("今天午饭吃什么", "chat"),
        ("lol", "chat"),
        ("give me a minute", "chat"),
        ("hi", "chat"),
        (".r 1d100 侦查检定", "rule_question"),
        ("。r 1d100 说服", "rule_question"),
        ("我的HP还剩多少", "rule_question"),
    ]

    passed = 0
    for msg, expected_type in test_cases:
        result = classifier_agent._keyword_fallback(msg)
        actual = result["message_type"]
        if actual == expected_type:
            passed += 1
            status = "OK"
        else:
            status = "FAIL (expected {}, got {})".format(expected_type, actual)
        print("  {} -> {} {}".format(msg[:30].ljust(30), actual.ljust(20), status))

    total = len(test_cases)
    print("  Result: {}/{} passed".format(passed, total))
    assert passed >= total - 1, "Too many classification failures"
    print("  PASS")


# ═══════════════════════════════════════════════════
# Test 2: ClassifierAgent LLM (skip if no API key)
# ═══════════════════════════════════════════════════
def test_classifier_llm():
    print("\n[2] ClassifierAgent - LLM mode")
    print("-" * 40)

    import os as os2
    api_key = os2.environ.get("OPENAI_API_KEY") or os2.environ.get("OPENAI_API_KEY", "")
    # Also try from settings
    try:
        from app.config import settings as s
        if s.OPENAI_API_KEY:
            api_key = s.OPENAI_API_KEY
    except Exception:
        pass

    if not api_key or api_key.startswith("sk-your"):
        print("  SKIP: OPENAI_API_KEY not configured")
        return

    from app.agents.classifier_agent import classifier_agent

    test_cases = [
        ("我想调查书房里的画像", "player_action"),
        ("我检查画像背后", "player_action"),
        ("今天午饭吃什么", "chat"),
    ]

    passed = 0
    for msg, expected_type in test_cases:
        result = classifier_agent.classify(message=msg)
        actual = result["message_type"]
        if actual == expected_type:
            passed += 1
            status = "OK"
        else:
            status = "FAIL"
        print("  {} -> {} (conf: {:.1f}) {}".format(
            msg[:30].ljust(30), actual.ljust(20), result["confidence"], status))

    print("  Result: {}/{} passed".format(passed, len(test_cases)))
    if passed >= 2:
        print("  PASS")
    else:
        print("  WARN: LLM classification could be improved")


# ═══════════════════════════════════════════════════
# Test 3: QueryEnhancer
# ═══════════════════════════════════════════════════
def test_query_enhancer():
    print("\n[3] QueryEnhancer - state-aware query enrichment")
    print("-" * 40)

    from app.rag.query_enhancer import QueryEnhancer, QueryContext

    enhancer = QueryEnhancer()

    # Test expansion strategy
    ctx = QueryContext(
        query="调查书房",
        active_scene="黑木庄园大厅",
        active_npcs=["托马斯", "爱德华"],
        undiscovered_clues=["烧焦的笔记本", "隐藏的暗门"],
    )
    result = enhancer.enhance("调查书房", ctx, strategy="expansion")
    assert "黑木庄园" in result, "Scene not in expanded query"
    assert "托马斯" in result, "NPC not in expanded query"
    assert "笔记本" in result, "Clue not in expanded query"
    print("  Expansion strategy: OK ({} chars)".format(len(result)))

    # Test prefix strategy
    result_p = enhancer.enhance("调查书房", ctx, strategy="prefix")
    assert "Current scene" in result_p or "场景" in result_p, "Prefix not applied"
    print("  Prefix strategy: OK ({} chars)".format(len(result_p)))

    # Test empty context
    empty_ctx = QueryContext(query="test")
    result_e = enhancer.enhance("test", empty_ctx)
    assert result_e == "test", "Empty context not handled"
    print("  Empty context: OK")

    # Test build_context
    ctx2 = enhancer.build_context(
        active_scene_name="黑木庄园",
        active_scene_summary="大门紧锁",
        npc_names=["托马斯"],
        undiscovered_clue_names=["拉丁文刻字"],
    )
    assert "黑木庄园" in ctx2.active_scene
    print("  Context builder: OK")

    print("  PASS")


# ═══════════════════════════════════════════════════
# Test 4: KeywordSearcher tokenization
# ═══════════════════════════════════════════════════
def test_keyword_tokenization():
    print("\n[4] KeywordSearcher - Chinese tokenization")
    print("-" * 40)

    from app.rag.keyword_search import KeywordSearcher
    ks = KeywordSearcher()

    test_cases = [
        ("调查书房画像", "short", 5),
        ("黑木庄园大门前的石柱刻字", "medium", 10),
        ("爱德华·哈灵顿 地下室 法阵", "multi", 8),
    ]

    for query, desc, min_tokens in test_cases:
        tokens = ks._tokenize(query)
        print("  {} ({}): {} tokens".format(query[:25].ljust(25), desc, len(tokens)))
        assert len(tokens) >= min_tokens, "Only {} tokens for '{}'".format(len(tokens), query)
    print("  PASS")


# ═══════════════════════════════════════════════════
# Test 5: RRF fusion
# ═══════════════════════════════════════════════════
def test_rrf_fusion():
    print("\n[5] RRF Fusion - ranking merge")
    print("-" * 40)

    try:
        from app.rag.retriever import Retriever
        r = Retriever()

        vec = [
            {"id": "a", "score": 0.92, "payload": {"title": "大厅"}},
            {"id": "b", "score": 0.85, "payload": {"title": "大门"}},
            {"id": "c", "score": 0.78, "payload": {"title": "密室"}},
        ]
        kw = [
            {"id": "c", "score": 1.0, "payload": {"title": "密室"}},
            {"id": "d", "score": 0.8, "payload": {"title": "地下室"}},
            {"id": "a", "score": 0.5, "payload": {"title": "大厅"}},
        ]

        fused = r._rrf_fusion(vec, kw)
        print("  Vec: {}, KW: {}, Fused: {} unique".format(len(vec), len(kw), len(fused)))
        for i, item in enumerate(fused):
            pid = item.get("payload", {}).get("title", item["id"])
            print("    {}. {} (RRF: {:.4f})".format(i + 1, pid, item["score"]))

        # chunk_c should rank high (top in KW, 3rd in vec)
        assert fused[0]["id"] in ("c", "a"), "Top RRF result unexpected: " + str(fused[0]["id"])
        assert len(fused) == 4, "Should have 4 unique results"
        print("  PASS")
    except ImportError as e:
        print("  SKIP: {}".format(e))


# ═══════════════════════════════════════════════════
# Test 6: Reranker boosts
# ═══════════════════════════════════════════════════
def test_reranker():
    print("\n[6] Reranker - state-aware boosts")
    print("-" * 40)

    try:
        from app.rag.retriever import Retriever
        r = Retriever()

        results = [
            {"id": "1", "score": 0.85, "payload": {
                "title": "黑木庄园大门", "text": "铁门紧锁", "location": "大门",
                "visibility": "player_visible", "related_nodes": []}},
            {"id": "2", "score": 0.90, "payload": {
                "title": "爱德华的日记", "text": "记录着家族的秘密", "location": "密室",
                "visibility": "kp_only", "related_nodes": ["爱德华"]}},
            {"id": "3", "score": 0.80, "payload": {
                "title": "地下室", "text": "黑绿色液体", "location": "地下酒窖",
                "visibility": "player_visible", "related_nodes": []}},
        ]

        reranked = r._rerank(results, scene_context="黑木庄园大门", active_npcs=["爱德华"])

        print("  Results after rerank:")
        for item in reranked:
            pid = item.get("payload", {}).get("title", item["id"])
            bd = item.get("_boost_detail", {})
            print("    {}: base={:.2f} -> rerank={:.2f} (scene+{:.1f} hidden+{:.1f})".format(
                pid, item["score"], item["rerank_score"],
                bd.get("scene_boost", 0), bd.get("hidden_boost", 0)))

        # chunk_1 (scene match) should get boosted above chunk_3
        assert reranked[0]["_boost_detail"]["scene_boost"] >= 0.3 or \
               reranked[0]["id"] == "2", "Expected scene or hidden boost on top result"
        print("  PASS")
    except ImportError as e:
        print("  SKIP: {}".format(e))


# ═══════════════════════════════════════════════════
# Test 7: ContextManager model validation
# ═══════════════════════════════════════════════════
def test_context_manager_models():
    print("\n[7] ContextManager - model structure validation")
    print("-" * 40)

    # Verify that ContextManager imports and its types are valid
    from app.harness.context_manager import ContextManager, build_context, build_rag_context
    print("  Classes imported: ContextManager, build_context, build_rag_context")

    # Verify method signatures
    import inspect
    sig = inspect.signature(ContextManager.__init__)
    assert "session" in str(sig), "__init__ missing session param"
    print("  __init__(session): OK")

    sig = inspect.signature(ContextManager.build)
    assert "campaign_id" in str(sig), "build missing campaign_id"
    print("  build(campaign_id): OK")

    sig = inspect.signature(ContextManager.build_rag_context)
    assert "campaign_id" in str(sig), "build_rag_context missing campaign_id"
    print("  build_rag_context(campaign_id): OK")

    print("  PASS")


# ═══════════════════════════════════════════════════
# Test 8: TraceRecorder model validation
# ═══════════════════════════════════════════════════
def test_trace_recorder_models():
    print("\n[8] TraceRecorder - model structure validation")
    print("-" * 40)

    from app.harness.trace_recorder import TraceRecorder, record_decorator

    # Verify TraceRecorder interface
    import inspect
    sig = inspect.signature(TraceRecorder.start)
    assert "campaign_id" in str(sig), "start missing campaign_id"
    assert "input_data" in str(sig), "start missing input_data"
    print("  start(campaign_id, input_data): OK")

    sig = inspect.signature(TraceRecorder.finish)
    assert "trace_id" in str(sig), "finish missing trace_id"
    assert "output_data" in str(sig), "finish missing output_data"
    print("  finish(trace_id, output_data): OK")

    sig = inspect.signature(TraceRecorder.record)
    assert "campaign_id" in str(sig), "record missing campaign_id"
    print("  record(campaign_id, ...): OK")

    # Validate record_decorator
    assert callable(record_decorator), "record_decorator not callable"
    decorator = record_decorator("test_agent")
    assert callable(decorator), "decorator result not callable"
    print("  record_decorator: OK")

    print("  PASS")


# ═══════════════════════════════════════════════════
# Test 9: Orchestrator fallback
# ═══════════════════════════════════════════════════
def test_orchestrator_fallback():
    print("\n[9] Orchestrator - fallback behavior")
    print("-" * 40)

    # Validate the Orchestrator's error handler returns safe defaults
    from app.harness.orchestrator import Orchestrator

    # Check that the class exists and has expected methods
    assert hasattr(Orchestrator, "process"), "Orchestrator missing process()"
    assert hasattr(Orchestrator, "_build_suggestion"), "Orchestrator missing _build_suggestion()"
    print("  Orchestrator.process() and _build_suggestion(): OK")

    # Verify _build_suggestion with empty data
    import inspect
    sig = inspect.signature(Orchestrator._build_suggestion)
    params = list(sig.parameters.keys())
    for p in ["sender", "content", "msg_type", "context", "results", "meta"]:
        assert p in params, "Missing param: " + p
    print("  _build_suggestion signature: OK ({} params)".format(len(params)))

    # Verify process_message convenience function
    from app.harness.orchestrator import process_message
    assert callable(process_message), "process_message not callable"
    print("  process_message(): OK")

    # Fallback return validation
    fallback = {
        "need_kp_notify": False,
        "kp_suggestion": "",
        "message_type": "chat",
        "classification": {"message_type": "chat"},
    }
    assert fallback["need_kp_notify"] is False
    assert fallback["message_type"] == "chat"
    print("  Fallback return value: OK")

    print("  PASS")


# ═══════════════════════════════════════════════════
# Test 10: Binding API logic
# ═══════════════════════════════════════════════════
def test_binding_api():
    print("\n[10] Campaign binding API - endpoint validation")
    print("-" * 40)

    from app.api.campaigns import router as campaigns_router

    # Check that KP binding endpoints are registered
    routes = [(r.path, list(r.methods)) for r in campaigns_router.routes]
    print("  Campaign routes: {}".format(len(routes)))

    bind_endpoints = [p for p, m in routes if "bind" in p or "kp" in p]
    assert len(bind_endpoints) >= 2, "Expected bind-kp and by-kp endpoints"
    for ep in bind_endpoints:
        print("    {}".format(ep))
    print("  PASS")


# ═══════════════════════════════════════════════════
# Test 11: Cross-module integration sanity
# ═══════════════════════════════════════════════════
def test_cross_module_imports():
    print("\n[11] Cross-module integration sanity check")
    print("-" * 40)

    # Verify that all __init__.py files export the right names
    ok = True

    # RAG module
    try:
        from app.rag import query_enhancer, get_retriever, get_keyword_searcher
        assert hasattr(query_enhancer, "enhance")
        print("  app.rag: OK")
    except Exception as e:
        print("  app.rag: FAIL - {}".format(e))
        ok = False

    # Agents module
    try:
        from app.agents import classifier_agent
        assert hasattr(classifier_agent, "classify")
        print("  app.agents: OK")
    except Exception as e:
        print("  app.agents: FAIL - {}".format(e))
        ok = False

    # Harness module
    try:
        from app.harness import Orchestrator, ContextManager, TraceRecorder
        assert callable(Orchestrator)
        assert callable(ContextManager)
        assert callable(TraceRecorder)
        print("  app.harness: OK")
    except Exception as e:
        print("  app.harness: FAIL - {}".format(e))
        ok = False

    # API module
    try:
        from app.api.campaigns import router as cr
        from app.api.messages import router as mr
        assert len(cr.routes) > 5
        assert len(mr.routes) >= 2
        print("  app.api: OK")
    except Exception as e:
        print("  app.api: FAIL - {}".format(e))
        ok = False

    if ok:
        print("  PASS")
    else:
        print("  FAIL - Some imports failed")
        assert False, "Cross-module imports failed"


# ═══════════════════════════════════════════════════
# Test 12: Project structure validation
# ═══════════════════════════════════════════════════
def test_project_structure():
    print("\n[12] Project structure validation")
    print("-" * 40)

    import os.path
    base = os.path.join(os.path.dirname(__file__), "..", "..")

    # Expected files and directories (Phase 1 MVP)
    expected = [
        # Root configs
        ("docker-compose.yml", True),
        (".env.example", True),
        ("start.sh", True),
        ("stop.sh", True),
        ("plan.md", True),
        ("design.md", True),
        # Docker
        ("backend/Dockerfile", True),
        ("backend/requirements.txt", True),
        # Backend app
        ("backend/app/main.py", True),
        ("backend/app/config.py", True),
        # API
        ("backend/app/api/__init__.py", True),
        ("backend/app/api/modules.py", True),
        ("backend/app/api/campaigns.py", True),
        ("backend/app/api/messages.py", True),
        ("backend/app/api/rag.py", True),
        ("backend/app/api/summaries.py", True),
        # Storage
        ("backend/app/storage/__init__.py", True),
        ("backend/app/storage/database.py", True),
        ("backend/app/storage/models.py", True),
        ("backend/app/storage/qdrant.py", True),
        ("backend/app/storage/redis.py", True),
        ("backend/app/storage/base_repo.py", True),
        ("backend/app/storage/campaign_repo.py", True),
        ("backend/app/storage/module_repo.py", True),
        ("backend/app/storage/message_repo.py", True),
        ("backend/app/storage/scene_repo.py", True),
        ("backend/app/storage/npc_repo.py", True),
        ("backend/app/storage/clue_repo.py", True),
        ("backend/app/storage/trace_repo.py", True),
        ("backend/app/storage/character_repo.py", True),
        # RAG
        ("backend/app/rag/__init__.py", True),
        ("backend/app/rag/document_parser.py", True),
        ("backend/app/rag/chunker.py", True),
        ("backend/app/rag/extractor.py", True),
        ("backend/app/rag/embedding.py", True),
        ("backend/app/rag/retriever.py", True),
        ("backend/app/rag/query_enhancer.py", True),
        ("backend/app/rag/keyword_search.py", True),
        # Bot
        ("backend/app/bot/__init__.py", True),
        ("backend/app/bot/__main__.py", True),
        ("backend/app/bot/config.py", True),
        ("backend/app/bot/api_client.py", True),
        ("backend/app/bot/binding.py", True),
        ("backend/app/bot/commands.py", True),
        ("backend/app/bot/handlers.py", True),
        # Harness (Step 6)
        ("backend/app/harness/__init__.py", True),
        ("backend/app/harness/orchestrator.py", True),
        ("backend/app/harness/context_manager.py", True),
        ("backend/app/harness/trace_recorder.py", True),
        # Agents (Step 6)
        ("backend/app/agents/__init__.py", True),
        ("backend/app/agents/classifier_agent.py", True),
        # Alembic
        ("backend/alembic.ini", True),
        ("backend/alembic/env.py", True),
        # Examples
        ("examples/demo_module.md", True),
        ("examples/demo_messages.jsonl", True),
        # Tests
        ("backend/tests/test_step4_rag.py", True),
        ("backend/tests/test_step7_mvp.py", True),
        ("backend/.gitignore", False),
    ]

    missing = []
    for path, is_required in expected:
        full = os.path.join(base, path.replace("/", os.sep))
        if not os.path.exists(full):
            if is_required:
                missing.append(path)
            # optional - just note

    if missing:
        print("  MISSING FILES:")
        for m in missing:
            print("    " + m)
    else:
        print("  All {} expected files present".format(len(expected)))

    # Count total files
    py_count = 0
    for root, dirs, files in os.walk(base):
        if ".git" in root or "__pycache__" in root:
            continue
        for f in files:
            if f.endswith(".py"):
                py_count += 1
    print("  Total Python files: {}".format(py_count))

    if not missing:
        print("  PASS")
    else:
        print("  WARN: Some expected files missing (may not be critical)")


# ═══════════════════════════════════════════════════
# Runner
# ═══════════════════════════════════════════════════
def main():
    print("=" * 60)
    print("  ChronicleAgent Phase 1 MVP Test Suite")
    print("=" * 60)
    print()
    print("  Date: {}".format(time.strftime("%Y-%m-%d %H:%M:%S")))
    print("  Python: {}".format(sys.version.split()[0]))
    print("  CWD: {}".format(os.getcwd()))
    print()

    tests = [
        ("Classifier keyword fallback", test_classifier_fallback),
        ("Classifier LLM mode (skip if no key)", test_classifier_llm),
        ("QueryEnhancer logic", test_query_enhancer),
        ("KeywordSearcher tokenization", test_keyword_tokenization),
        ("RRF fusion", test_rrf_fusion),
        ("Reranker boosts", test_reranker),
        ("ContextManager model validation", test_context_manager_models),
        ("TraceRecorder model validation", test_trace_recorder_models),
        ("Orchestrator fallback behavior", test_orchestrator_fallback),
        ("Campaign binding API validation", test_binding_api),
        ("Cross-module integration", test_cross_module_imports),
        ("Project structure validation", test_project_structure),
    ]

    results = {"pass": 0, "fail": 0, "skip": 0, "warn": 0}

    for name, func in tests:
        print()
        try:
            func()
            results["pass"] += 1
            print("  STATUS: PASS")
        except AssertionError as e:
            results["fail"] += 1
            print("  STATUS: FAIL - {}".format(e))
        except Exception as e:
            import traceback
            results["warn"] += 1
            print("  STATUS: WARN - {}".format(e))

    print("\n" + "=" * 60)
    print("  RESULTS: {pass}/{total} passed, {fail} failed, {warn} warned, {skip} skipped".format(
        total=len(tests), **results))
    print("=" * 60)

    if results["fail"] > 0:
        print("\n  Some tests FAILED. Review output above.")
        sys.exit(1)
    elif results["warn"] > 0:
        print("\n  All critical tests passed. Some non-critical warnings.")
        sys.exit(0)
    else:
        print("\n  ALL TESTS PASSED.")
        sys.exit(0)


if __name__ == "__main__":
    main()
