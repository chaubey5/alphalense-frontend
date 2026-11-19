import { useCallback, useEffect, useReducer, useRef } from "react";
import { apiUrl } from "@/lib/api";

const initialState = {
  marketData: null,
  agents: {},
  steps: [],
  status: {},
  error: null,
  done: false,
  loading: true,
};

function reducer(state, action) {
  switch (action.type) {
    case "reset":         return { ...initialState };
    case "push_step":     return { ...state, steps: [...state.steps, action.step] };
    case "market_data":   return { ...state, marketData: action.payload };
    case "agent_start":   return { ...state, status: { ...state.status, [action.agent]: "running" } };
    case "agent_done":    return {
      ...state,
      status: { ...state.status, [action.agent]: "done" },
      agents: { ...state.agents, [action.agent]: action.data || {} },
    };
    case "agent_error":   return {
      ...state,
      status: { ...state.status, [action.agent]: "error" },
    };
    case "set_error":     return {
      ...state,
      error: action.message,
      status: Object.fromEntries(
        Object.entries(state.status).map(([agent, status]) => [
          agent,
          status === "running" ? "error" : status,
        ]),
      ),
      done: true,
      loading: false,
    };
    case "complete":      return { ...state, done: true, loading: false };
    default:              return state;
  }
}

/**
 * Subscribe to the SSE multi-agent research pipeline for a given ticker.
 * Returns reactive state + a `restart` callback.
 */
export default function useResearchPipeline(ticker, agentLabels = {}) {
  const [state, dispatch] = useReducer(reducer, initialState);
  const labelsRef = useRef(agentLabels);

  // Keep latest labels accessible without rebinding the effect.
  useEffect(() => { labelsRef.current = agentLabels; }, [agentLabels]);

  const pushStep = useCallback((text) => {
    dispatch({ type: "push_step", step: { t: Date.now(), text } });
  }, []);

  const safeParse = useCallback((data) => {
    try { return JSON.parse(data); } catch (err) {
      console.error("SSE JSON parse failed:", err, data);
      return null;
    }
  }, []);

  useEffect(() => {
    if (!ticker) return undefined;
    dispatch({ type: "reset" });

    const url = `${apiUrl("research/start")}?ticker=${encodeURIComponent(ticker)}`;
    const es = new EventSource(url);

    const onInit = () => pushStep(`Pipeline initialised for ${ticker}.`);
    const onStep = (e) => { const d = safeParse(e.data); if (d?.label) pushStep(d.label); };
    const onMarket = (e) => {
      const d = safeParse(e.data);
      if (d) { dispatch({ type: "market_data", payload: d }); pushStep("Market data fetched."); }
    };
    const onAgentStart = (e) => {
      const d = safeParse(e.data); if (!d?.agent) return;
      dispatch({ type: "agent_start", agent: d.agent });
      pushStep(`${d.label || d.agent} started.`);
    };
    const onAgentDone = (e) => {
      const d = safeParse(e.data); if (!d?.agent) return;
      dispatch({ type: "agent_done", agent: d.agent, data: d.data });
      pushStep(`${labelsRef.current[d.agent] || d.agent} agent finished.`);
    };
    const onAgentError = (e) => {
      const d = safeParse(e.data); if (!d?.agent) return;
      dispatch({ type: "agent_error", agent: d.agent });
      pushStep(d.message || `${labelsRef.current[d.agent] || d.agent} agent failed.`);
    };
    const onError = (e) => {
      if (typeof e.data !== "string") {
        dispatch({
          type: "set_error",
          message: "Could not connect to the research service. Check the backend URL and try again.",
        });
        es.close();
        return;
      }
      const d = safeParse(e.data);
      dispatch({
        type: "set_error",
        message: d?.message || "The research service returned an unreadable error.",
      });
      pushStep(d?.message || "The research service returned an unreadable error.");
      es.close();
    };
    const onWarning = (e) => {
      const d = safeParse(e.data);
      if (d?.message) pushStep(`Warning: ${d.message}`);
    };
    const onComplete = () => {
      dispatch({ type: "complete" });
      pushStep("Report complete.");
      es.close();
    };
    es.addEventListener("init", onInit);
    es.addEventListener("step", onStep);
    es.addEventListener("market_data", onMarket);
    es.addEventListener("agent_start", onAgentStart);
    es.addEventListener("agent_done", onAgentDone);
    es.addEventListener("agent_error", onAgentError);
    es.addEventListener("error", onError);
    es.addEventListener("warning", onWarning);
    es.addEventListener("complete", onComplete);

    return () => { es.close(); };
  }, [ticker, pushStep, safeParse]);

  return state;
}
