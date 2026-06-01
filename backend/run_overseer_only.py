"""One-shot script: run just the overseer phase using cached sub-agent results."""
import asyncio
import logging
from datetime import UTC, datetime

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("run_overseer_only")


async def main() -> None:
    from app.agents.base import AgentResult
    from app.agents.debate_agents import run_debate_round
    from app.agents.llm_client import make_overseer_client
    from app.agents.memory import save_agent_memories
    from app.agents.overseer import run_overseer
    from app.constants import REDIS_AGENT_ANALYSIS_KEY, REDIS_AGENT_META_KEY, REDIS_PORTFOLIO_RISK_KEY
    from app.core.redis_client import cache_load_json, cache_save_json
    from app.db.session import async_session_factory
    from app.services.recommendations_service import get_agent_calibration, save_recommendations
    from app.agents.tools import ToolContext

    # Load cached pipeline data
    logger.info("Loading cached sub-agent results from Redis...")
    data = await cache_load_json(REDIS_AGENT_ANALYSIS_KEY)
    if not data:
        logger.error("No cached analysis found. Run the full pipeline first.")
        return

    run_id = data["run_id"]
    logger.info("Using run_id=%s", run_id)

    # Reconstruct AgentResult objects
    sub_results = [
        AgentResult(name=r["name"], text=r.get("text", ""), parsed=r.get("parsed", {}), error=r.get("error"))
        for r in data.get("sub_reports", [])
    ]
    cr = data.get("catalyst_report") or {}
    br = data.get("bear_report") or {}
    catalyst_result = AgentResult(name="catalyst", text=cr.get("text", ""), parsed=cr.get("parsed", {}), error=cr.get("error")) if cr else None
    bear_result = AgentResult(name="bear_case", text=br.get("text", ""), parsed=br.get("parsed", {}), error=br.get("error")) if br else None

    logger.info(
        "Loaded: %d sub-agents, catalyst=%s, bear=%s",
        len(sub_results),
        "ok" if catalyst_result and not catalyst_result.error else "missing",
        "ok" if bear_result and not bear_result.error else "missing",
    )

    # Build tool context and load context data
    tool_context = ToolContext(session_factory=async_session_factory, top_n=10)
    risk_context = await cache_load_json(REDIS_PORTFOLIO_RISK_KEY)

    try:
        async with async_session_factory() as cal_session:
            calibration = await get_agent_calibration(cal_session)
    except Exception as exc:
        logger.warning("Calibration load failed: %s", exc)
        calibration = {}

    # Create overseer client (Anthropic)
    o_client, o_model = make_overseer_client()
    logger.info("Overseer client: %s, model: %s", type(o_client).__name__, o_model)

    # Phase 3 — overseer initial synthesis
    logger.info("Running overseer initial synthesis...")
    overseer_result = await run_overseer(
        sub_results, catalyst_result, bear_result, o_client, tool_context,
        risk_context=risk_context,
        agent_calibration=calibration,
    )
    logger.info("Overseer done. error=%s, trades=%d",
        overseer_result.error,
        len(overseer_result.parsed.get("verified_trades", [])),
    )

    # Phase 4 — debate round
    summaries = {r.name: r.parsed.get("summary", r.text[:200]) for r in sub_results if not r.error}
    debate_results: dict = {"bull_debates": {}, "bear_rebuttals": {}}

    if overseer_result.error is None and overseer_result.parsed.get("verified_trades"):
        strong_buys = [t["ticker"] for t in overseer_result.parsed["verified_trades"] if t.get("final_recommendation") == "STRONG_BUY"]
        avoids = [t["ticker"] for t in overseer_result.parsed["verified_trades"] if t.get("final_recommendation") == "AVOID"]

        if strong_buys or avoids:
            logger.info("Running debate round — %d STRONG_BUY, %d AVOID", len(strong_buys), len(avoids))
            try:
                debate_results = await run_debate_round(
                    overseer_result.parsed,
                    bear_result.parsed if bear_result and not bear_result.error else {},
                    summaries,
                    o_client,
                    tool_context,
                )
                if debate_results["bull_debates"] or debate_results["bear_rebuttals"]:
                    logger.info("Re-running overseer with debate context...")
                    overseer_result = await run_overseer(
                        sub_results, catalyst_result, bear_result, o_client, tool_context,
                        debate_context=debate_results,
                        risk_context=risk_context,
                        agent_calibration=calibration,
                    )
            except Exception as exc:
                logger.error("Debate round failed: %s", exc)

    # Save results back to Redis
    overseer_ok = overseer_result.error is None and bool(overseer_result.parsed.get("verified_trades"))
    verified_trades = overseer_result.parsed.get("verified_trades", []) if overseer_ok else []
    logger.info("Overseer ok=%s, verified_trades=%d", overseer_ok, len(verified_trades))

    updated_data = {**data}
    updated_data["overseer"] = {"text": overseer_result.text, "parsed": overseer_result.parsed, "error": overseer_result.error}
    updated_data["debate_report"] = debate_results
    updated_data["generated_at"] = datetime.now(tz=UTC).isoformat()

    await cache_save_json(REDIS_AGENT_ANALYSIS_KEY, updated_data)

    meta = await cache_load_json(REDIS_AGENT_META_KEY) or {}
    meta.update({
        "overseer_ok": overseer_ok,
        "debate_tickers": list(debate_results.get("bull_debates", {}).keys()),
        "generated_at": updated_data["generated_at"],
    })
    await cache_save_json(REDIS_AGENT_META_KEY, meta)

    # Save recommendations to DB if we got trades
    if verified_trades:
        try:
            async with async_session_factory() as rec_session:
                await save_recommendations(run_id, verified_trades, rec_session)
            logger.info("Saved %d recommendations to DB", len(verified_trades))
        except Exception as exc:
            logger.error("Failed to save recommendations: %s", exc)

    logger.info("Done. Overseer result saved to Redis.")
    if verified_trades:
        for t in verified_trades:
            logger.info("  %s — %s", t.get("ticker"), t.get("final_recommendation"))


if __name__ == "__main__":
    asyncio.run(main())
