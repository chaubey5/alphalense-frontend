import { useCallback, useEffect, useRef, useState } from "react";
import axios from "axios";
import { useNavigate } from "react-router-dom";
import { Search, Loader2, TrendingUp } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const DROPDOWN_INIT = { opacity: 0, y: -6 };
const DROPDOWN_ANIM = { opacity: 1, y: 0 };
const DROPDOWN_EXIT = { opacity: 0, y: -6 };
const PILL_RADIUS = { borderRadius: 999 };

export default function SearchBar({ size = "lg", autoFocus = false }) {
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const debounceRef = useRef(null);
  const navigate = useNavigate();

  const choose = useCallback((tickerSym) => {
    setOpen(false);
    setQ("");
    navigate(`/research/${tickerSym}`);
  }, [navigate]);

  useEffect(() => {
    if (!q || q.length < 1) {
      setResults([]);
      return undefined;
    }
    setLoading(true);
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      try {
        const { data } = await axios.get(`${API}/search`, { params: { q } });
        setResults(data.results || []);
        setOpen(true);
      } catch (err) {
        console.error("search failed:", err);
        setResults([]);
      } finally {
        setLoading(false);
      }
    }, 220);
    return () => clearTimeout(debounceRef.current);
  }, [q]);

  const submit = useCallback(() => {
    if (results[0]) choose(results[0].ticker);
    else if (q.trim()) choose(q.trim().toUpperCase());
  }, [results, q, choose]);

  const onKey = useCallback((e) => {
    if (e.key === "Enter") submit();
    if (e.key === "Escape") setOpen(false);
  }, [submit]);

  const big = size === "lg";
  const padding = big ? "px-5 py-4" : "px-4 py-3";
  const iconSize = big ? "w-5 h-5" : "w-4 h-4";
  const inputSize = big ? "text-lg" : "text-base";
  const buttonSize = big ? "px-5 py-2.5 text-sm" : "px-4 py-2 text-xs";

  return (
    <div className="relative w-full" data-testid="search-container">
      <div
        className={`glass glass-strong flex items-center gap-3 ${padding} tilt`}
        style={PILL_RADIUS}
      >
        <Search className={`${iconSize} text-[var(--text-dim)]`} />
        <input
          autoFocus={autoFocus}
          data-testid="search-input"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onFocus={() => { if (results.length) setOpen(true); }}
          onBlur={() => setTimeout(() => setOpen(false), 200)}
          onKeyDown={onKey}
          placeholder="Search a company or ticker — e.g. Apple, NVDA, Tesla"
          className={`flex-1 bg-transparent outline-none placeholder:text-[var(--text-faint)] ${inputSize}`}
        />
        {loading && <Loader2 className="w-4 h-4 animate-spin text-[var(--text-dim)]" />}
        <button
          data-testid="search-submit-btn"
          onClick={submit}
          className={`btn-primary ${buttonSize} rounded-full flex items-center gap-2`}
        >
          <TrendingUp className="w-4 h-4" /> Analyze
        </button>
      </div>

      <AnimatePresence>
        {open && results.length > 0 && (
          <motion.div
            initial={DROPDOWN_INIT}
            animate={DROPDOWN_ANIM}
            exit={DROPDOWN_EXIT}
            className="absolute mt-2 left-0 right-0 glass z-50 overflow-hidden"
            data-testid="search-results-dropdown"
          >
            {results.slice(0, 7).map((r) => (
              <button
                key={r.ticker}
                onMouseDown={() => choose(r.ticker)}
                data-testid={`search-result-${r.ticker}`}
                className="w-full text-left px-5 py-3 flex items-center justify-between hover:bg-white/[0.04] transition-colors border-b border-[var(--border)] last:border-b-0"
              >
                <div className="flex flex-col">
                  <span className="font-mono text-sm text-[var(--accent)]">{r.ticker}</span>
                  <span className="text-sm text-[var(--text-dim)]">{r.name}</span>
                </div>
                <span className="label-eyebrow">{r.exchange || r.currency}</span>
              </button>
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
