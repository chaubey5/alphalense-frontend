import { useCallback, useEffect, useReducer, useRef } from "react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const initialState = {
  marketData: null,
  agents: {},
  steps: [],
  status: {},
  error: null,
  done: false,
};

function reducer(state, action) {
  switch (action.type) {
    case "reset":         return initialState;
    case "push_step":     return { ...state, steps: [...state.steps, action.step] };
    case "market_data":   return { ...state, marketData: action.payload };
    case "agent_start":   return { ...state, status: { ...state.status, [action.agent]: "running" } };
    case "agent_done":    return {
      ...state,
      status: { ...state.status, [action.agent]: "done" },
      agents: { ...state.agents, [action.agent]: action.data || {} },
    };
    case "set_error":     return { ...state, error: action.message };
    case "complete":      return { ...state, done: true };
    default:              return state;
  }
}

/**
 * Subscribe to the SSE multi-agent research pipeline for a given ticker.
 * Returns reactive state + a `restart` callback.
 */
export default function useResearchPipeline(ticker, agentLabels = {}) {
  const [state, dispatch] = useReducer(reducer, initialState);
  const esRef = useRef(null);
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

    const url = `${API}/research/start?ticker=${encodeURIComponent(ticker)}`;
    const es = new EventSource(url);
    esRef.current = es;

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
    const onError = (e) => {
      const d = safeParse(e.data); if (d?.message) dispatch({ type: "set_error", message: d.message });
    };
    const onComplete = () => {
      dispatch({ type: "complete" });
      pushStep("Report complete.");
      es.close();
    };
    const onTransportError = (err) => {
      // EventSource fires onerror on normal close after stream completes — log only when truly unexpected.
      if (es.readyState !== EventSource.CLOSED) {
        console.warn("SSE transport error:", err);
      }
    };

    es.addEventListener("init", onInit);
    es.addEventListener("step", onStep);
    es.addEventListener("market_data", onMarket);
    es.addEventListener("agent_start", onAgentStart);
    es.addEventListener("agent_done", onAgentDone);
    es.addEventListener("error", onError);
    es.addEventListener("complete", onComplete);
    es.onerror = onTransportError;

    return () => { es.close(); };
  }, [ticker, pushStep, safeParse]);

  return state;
}
