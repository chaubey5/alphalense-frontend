import { useEffect, useRef, useState } from "react";
import axios from "axios";
import { useNavigate } from "react-router-dom";
import { Search, Loader2, TrendingUp } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function SearchBar({ size = "lg", autoFocus = false }) {
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const debounceRef = useRef(null);
  const navigate = useNavigate();

  useEffect(() => {
    if (!q || q.length < 1) { setResults([]); return; }
    setLoading(true);
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      try {
        const { data } = await axios.get(`${API}/search`, { params: { q } });
        setResults(data.results || []);
        setOpen(true);
      } catch (e) {
        setResults([]);
      } finally { setLoading(false); }
    }, 220);
    return () => clearTimeout(debounceRef.current);
  }, [q]);

  const choose = (t) => {
    setOpen(false); setQ("");
    navigate(`/research/${t}`);
  };

  const onKey = (e) => {
    if (e.key === "Enter") {
      if (results.length > 0) choose(results[0].ticker);
      else if (q.trim()) choose(q.trim().toUpperCase());
    }
    if (e.key === "Escape") setOpen(false);
  };

  const big = size === "lg";

  return (
    <div className="relative w-full" data-testid="search-container">
      <div
        className={`glass glass-strong flex items-center gap-3 ${big ? "px-5 py-4" : "px-4 py-3"} tilt`}
        style={{ borderRadius: 999 }}
      >
        <Search className={`${big ? "w-5 h-5" : "w-4 h-4"} text-[var(--text-dim)]`} />
        <input
          autoFocus={autoFocus}
          data-testid="search-input"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onFocus={() => results.length && setOpen(true)}
          onBlur={() => setTimeout(() => setOpen(false), 200)}
          onKeyDown={onKey}
          placeholder="Search a company or ticker — e.g. Apple, NVDA, Tesla"
          className={`flex-1 bg-transparent outline-none placeholder:text-[var(--text-faint)] ${big ? "text-lg" : "text-base"}`}
        />
        {loading && <Loader2 className="w-4 h-4 animate-spin text-[var(--text-dim)]" />}
        <button
          data-testid="search-submit-btn"
          onClick={() => { if (results[0]) choose(results[0].ticker); else if (q) choose(q.toUpperCase()); }}
          className={`btn-primary ${big ? "px-5 py-2.5 text-sm" : "px-4 py-2 text-xs"} rounded-full flex items-center gap-2`}
        >
          <TrendingUp className="w-4 h-4" /> Analyze
        </button>
      </div>

      <AnimatePresence>
        {open && results.length > 0 && (
          <motion.div
            initial={{ opacity: 0, y: -6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            className="absolute mt-2 left-0 right-0 glass z-50 overflow-hidden"
            data-testid="search-results-dropdown"
          >
            {results.slice(0, 7).map((r, i) => (
              <button
                key={`${r.ticker}-${i}`}
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
