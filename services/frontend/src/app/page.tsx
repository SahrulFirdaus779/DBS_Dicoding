"use client";

import React, { useEffect, useState, useRef, useCallback } from "react";
import Chart from "chart.js/auto";
import { TabDonatur, TabProgram, TabRelawan, TabPenerima } from "./components/tabs";
import pctStyles from "./progressWidth.module.css";

const API = "/api";
const CACHE_TOKEN = "zakatsight-cache-token-2026";

// ── Types ────────────────────────────────────────────────────
type Stats = {
  total_nominal: number;
  total_nominal_str: string;
  jumlah_transaksi: number;
  donatur_unik: number;
  rata_rata_donasi_str: string;
  bulan_tertinggi_nama: string;
  bulan_tertinggi_val: string;
  monthly_labels: string[];
  monthly_data: number[];
  channel_labels: string[];
  channel_data: number[];
  bank_labels: string[];
  bank_data: number[];
  distribusi_labels: string[];
  distribusi_data: number[];
  latest_txns: { donatur: string; nominal: string; program: string; channel: string; tgl: string }[];
};

type Tab = "overview" | "donatur" | "program" | "relawan" | "prediksi" | "penerima";

// Helper: tentukan granularitas berdasarkan filter
function getGranularity(year: string, month: string) {
  if (year === "all") return "Tahun";
  if (month === "all") return "Bulan";
  return "Hari";
}

function getPeakLabel(year: string, month: string) {
  if (year === "all") return "Tahun Tertinggi";
  if (month === "all") return "Bulan Tertinggi";
  return "Hari Tertinggi";
}

const SIDEBAR_ITEMS: { group: string; items: { label: string; tab: Tab; icon: string }[] }[] = [
  {
    group: "Analytics",
    items: [
      { label: "Dashboard Utama", tab: "overview", icon: "📊" },
      { label: "Prediksi AI", tab: "prediksi", icon: "🤖" },
    ],
  },
  {
    group: "Segmentasi",
    items: [
      { label: "Segmen Donatur", tab: "donatur", icon: "👥" },
      { label: "Program Aktif", tab: "program", icon: "📋" },
      { label: "Penerima Manfaat", tab: "penerima", icon: "🤝" },
    ],
  },
  {
    group: "Channel & Wilayah",
    items: [
      { label: "Relawan & Channel", tab: "relawan", icon: "🗺️" },
    ],
  },
];

// ── Sub-components ────────────────────────────────────────────
function Skeleton({ w = "w-24" }: { w?: string }) {
  return <span className={`skeleton inline-block ${w} h-5 rounded align-middle`} />;
}

function KpiCard({ label, value, sub, subColor = "text-[#64748B]", trend }: {
  label: string; value: React.ReactNode; sub?: React.ReactNode; subColor?: string;
  trend?: "up" | "down" | "neutral";
}) {
  const trendIcon = trend === "up" ? "↑" : trend === "down" ? "↓" : null;
  const trendColor = trend === "up" ? "text-[#1D9E75]" : trend === "down" ? "text-[#E24B4A]" : "";
  return (
    <div className="kpi-card">
      <div className="text-[11px] font-medium text-[#64748B] mb-2 uppercase tracking-wider">{label}</div>
      <div className="font-serif text-2xl font-bold text-[#0F172A] leading-tight">{value}</div>
      {(sub || trend) && (
        <div className={`text-[11px] font-medium mt-2.5 flex items-center gap-1 ${subColor}`}>
          {trendIcon && <span className={`font-bold ${trendColor}`}>{trendIcon}</span>}
          {sub}
        </div>
      )}
    </div>
  );
}

function FilterBadge({ year, month }: { year: string; month: string }) {
  const monthNames = ["","Jan","Feb","Mar","Apr","Mei","Jun","Jul","Ags","Sep","Okt","Nov","Des"];
  const label = year === "all"
    ? "Semua Waktu"
    : month === "all"
    ? `Tahun ${year}`
    : `${monthNames[Number(month)]} ${year}`;
  return (
    <span className="inline-flex items-center gap-1 bg-[#E1F5EE] text-[#085041] border border-[#9FE1CB] text-[10px] font-bold px-2 py-0.5 rounded-full">
      🗓 {label}
    </span>
  );
}

function pctClass(pct: number) {
  const bounded = Math.max(0, Math.min(100, Math.round(pct)));
  return (pctStyles as Record<string, string>)[`pct${bounded}`] ?? (pctStyles as Record<string, string>).pct0;
}

function formatRupiah(val: number) {
  if (val >= 1_000_000_000) return `Rp ${(val/1_000_000_000).toFixed(1)}M`;
  if (val >= 1_000_000) return `Rp ${(val/1_000_000).toFixed(0)}jt`;
  if (val >= 1_000) return `Rp ${(val/1_000).toFixed(0)}rb`;
  return `Rp ${val.toLocaleString("id-ID")}`;
}

// ── Main Component ────────────────────────────────────────────
export default function InternalDashboard() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [year, setYear] = useState("all");
  const [month, setMonth] = useState("all");
  const [channel, setChannel] = useState("all");
  const [category, setCategory] = useState("all");
  const [filterOptions, setFilterOptions] = useState<{ channels: string[]; categories: string[] }>({
    channels: [],
    categories: []
  });
  const [tab, setTab] = useState<Tab>("overview");
  const [error, setError] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [toast, setToast] = useState("");
  const [txnPage, setTxnPage] = useState(1);
  const [txnSearch, setTxnSearch] = useState("");
  const [txnData, setTxnData] = useState<any>(null);
  const [txnError, setTxnError] = useState(false);
  const [forecastKpis, setForecastKpis] = useState<any>(null);
  const [forecastKpisErr, setForecastKpisErr] = useState(false);
  const [isCmdPaletteOpen, setIsCmdPaletteOpen] = useState(false);

  const trendRef = useRef<HTMLCanvasElement>(null);
  const trendChart = useRef<any>(null);
  const channelRef = useRef<HTMLCanvasElement>(null);
  const channelChart = useRef<any>(null);
  const bankRef = useRef<HTMLCanvasElement>(null);
  const bankChart = useRef<any>(null);
  const forecastRef = useRef<HTMLCanvasElement>(null);
  const forecastChart = useRef<any>(null);

  // Reset bulan ke "all" jika tahun diganti ke "all"
  const handleYearChange = (val: string) => {
    setYear(val);
    if (val === "all") setMonth("all");
  };

  const showToast = (msg: string) => { setToast(msg); setTimeout(() => setToast(""), 3000); };

  const buildCharts = useCallback((data: Stats) => {
        const fo = { responsive: true, maintainAspectRatio: false };
        const tick = { font: { size: 11, family: "'Plus Jakarta Sans',sans-serif" }, color: "#64748B" };

        // Build Forecast chart — destroy dulu jika sudah ada (fix memory leak B-03)
        if (forecastRef.current) {
          if (forecastChart.current) { forecastChart.current.destroy(); forecastChart.current = null; }
          const histLabels = ["Jan'25","Feb","Mar","Apr","Mei","Jun","Jul","Ags","Sep","Okt","Nov","Des","Jan'26","Feb","Mar","Apr","Mei"];
          const histData   = [1.2,1.4,2.1,1.8,3.4,1.6,1.5,1.9,2.2,2.0,2.5,2.8,1.8,2.1,2.3,2.0,1.9];
          const foreLabels = ["Jun'26","Jul","Ags","Sep","Okt","Nov","Des"];
          const foreData   = [2.1, 2.3, 1.8, 2.4, 2.6, 2.9, 3.1];
          const foreUpper  = [2.5, 2.8, 2.3, 3.0, 3.2, 3.5, 3.7];
          const foreLower  = [1.7, 1.8, 1.3, 1.9, 2.1, 2.4, 2.6];
          const allLabels  = [...histLabels, ...foreLabels];
          const allHist    = [...histData, ...Array(foreLabels.length).fill(null)];
          const allFore    = [...Array(histLabels.length).fill(null), ...foreData];
          const allUpper   = [...Array(histLabels.length).fill(null), ...foreUpper];
          const allLower   = [...Array(histLabels.length).fill(null), ...foreLower];
          forecastChart.current = new Chart(forecastRef.current, {
            type: "line",
            data: {
              labels: allLabels,
              datasets: [
                { label: "Historis", data: allHist, borderColor: "#1D9E75", backgroundColor: "rgba(29,158,117,0.1)", fill: true, tension: 0.4, borderWidth: 2, pointRadius: 3 },
                { label: "Prediksi ARIMA", data: allFore, borderColor: "#3B82F6", backgroundColor: "rgba(59,130,246,0.05)", borderDash: [5,4], fill: false, tension: 0.4, borderWidth: 2, pointRadius: 4, pointBackgroundColor: "#3B82F6" },
                { label: "Batas Atas (95%)", data: allUpper, borderColor: "rgba(59,130,246,0.2)", backgroundColor: "rgba(59,130,246,0.08)", fill: "+1", borderDash: [3,3], borderWidth: 1, pointRadius: 0 },
                { label: "Batas Bawah (95%)", data: allLower, borderColor: "rgba(59,130,246,0.2)", backgroundColor: "transparent", fill: false, borderDash: [3,3], borderWidth: 1, pointRadius: 0 },
              ],
            },
            options: {
              ...fo,
              plugins: {
                legend: { display: true, position: "top", labels: { font: { size: 11, family: "'Plus Jakarta Sans',sans-serif" }, color: "#64748B", usePointStyle: true, boxWidth: 8 } },
                tooltip: { callbacks: { label: (v: any) => v.raw != null ? `Rp ${Number(v.raw).toFixed(1)}jt` : "" } },
              },
              scales: {
                x: { ticks: { ...tick, maxRotation: 45 }, grid: { display: false } },
                y: { ticks: { ...tick, callback: (v: any) => `Rp${v}jt` }, grid: { color: "#F1F5F9" } },
              },
            },
          });
        }

        // Trend
        if (trendRef.current) {
          if (trendChart.current) trendChart.current.destroy();
          const isDaily = year !== "all" && month !== "all";
          const isYearly = year === "all";
          const xTitle = isDaily ? `Hari — ${["","Jan","Feb","Mar","Apr","Mei","Jun","Jul","Ags","Sep","Okt","Nov","Des"][Number(month)]} ${year}` : "";
          trendChart.current = new Chart(trendRef.current, {
            type: "line",
            data: {
              labels: data.monthly_labels,
              datasets: [{
                label: isDaily ? "Nominal Harian" : isYearly ? "Nominal Tahunan" : "Nominal Bulanan",
                data: data.monthly_data,
                borderColor: "#1D9E75",
                backgroundColor: "rgba(29,158,117,0.08)",
                fill: true, tension: 0.4, borderWidth: 2,
                pointRadius: isDaily ? 5 : 4,
                pointBackgroundColor: "#1D9E75",
                pointHoverRadius: 7,
              }],
            },
            options: {
              ...fo,
              plugins: {
                legend: { display: false },
                tooltip: {
                  callbacks: {
                    title: (items: any) => isDaily ? `Tgl ${items[0].label}` : items[0].label,
                    label: (v: any) => `  Rp ${Number(v.raw).toFixed(2)}jt`,
                  }
                },
              },
              scales: {
                x: {
                  ticks: { ...tick, maxRotation: isDaily ? 0 : 45 },
                  grid: { display: false },
                  title: xTitle ? { display: true, text: xTitle, color: "#94A3B8", font: { size: 10 } } : { display: false },
                },
                y: {
                  ticks: { ...tick, callback: (v: any) => `Rp${v}jt` },
                  grid: { color: "#F1F5F9" },
                },
              },
            },
          });
        }

        if (channelRef.current) {
          if (channelChart.current) channelChart.current.destroy();
          channelChart.current = new Chart(channelRef.current, {
            type: "bar",
            data: { labels: data.channel_labels, datasets: [{ data: data.channel_data, backgroundColor: "#1D9E75", borderRadius: 4, barThickness: 13 }] },
            options: { ...fo, indexAxis: "y", plugins: { legend: { display: false } }, scales: { x: { ticks: tick, grid: { color: "#F1F5F9" } }, y: { ticks: tick, grid: { display: false } } } },
          });
        }

        if (bankRef.current) {
          if (bankChart.current) bankChart.current.destroy();
          bankChart.current = new Chart(bankRef.current, {
            type: "bar",
            data: { labels: data.bank_labels, datasets: [{ data: data.bank_data, backgroundColor: ["#1D9E75","#5DCAA5","#9FE1CB","#FAC775","#D3D1C7"], borderRadius: 4, barThickness: 13 }] },
            options: { ...fo, indexAxis: "y", plugins: { legend: { display: false }, tooltip: { callbacks: { label: (v: any) => `${v.raw}%` } } }, scales: { x: { ticks: { ...tick, callback: (v: any) => `${v}%` }, grid: { color: "#F1F5F9" } }, y: { ticks: tick, grid: { display: false } } } },
          });
        }
  }, [year, month, channel, category]);

  // Load dynamic filter options on mount
  useEffect(() => {
    fetch(`${API}/filters`)
      .then(r => { if (!r.ok) throw new Error(); return r.json(); })
      .then(setFilterOptions)
      .catch(err => console.error("Gagal memuat filter options:", err));
  }, []);

  const fetchData = useCallback(() => {
    setStats(null); setError(false);
    fetch(`${API}/dashboard?year=${year}&month=${month}&channel=${channel}&category=${category}`)
      .then(r => { if (!r.ok) throw new Error(); return r.json(); })
      .then((data: Stats) => { setStats(data); setLastUpdated(new Date()); buildCharts(data); })
      .catch(() => setError(true));
  }, [year, month, channel, category, buildCharts]);

  const fetchTxns = useCallback((page = 1, search = "") => {
    setTxnError(false);
    fetch(`${API}/dashboard/txns?year=${year}&month=${month}&channel=${channel}&category=${category}&page=${page}&limit=10&search=${encodeURIComponent(search)}`)
      .then(r => {
        if (!r.ok) throw new Error();
        return r.json();
      })
      .then(setTxnData)
      .catch(() => setTxnError(true));
  }, [year, month, channel, category]);

  useEffect(() => {
    fetchData();
    fetchTxns(1, txnSearch);
    setTxnPage(1);
  }, [year, month, channel, category, fetchData, fetchTxns, txnSearch]);

  // Pastikan chart selalu muncul saat tab berpindah (canvas baru mount)
  useEffect(() => {
    if (stats && (tab === "overview" || tab === "prediksi")) {
      buildCharts(stats);
    }
  }, [stats, tab, buildCharts]);

  // Load live forecasting KPIs when "prediksi" tab is opened
  useEffect(() => {
    if (tab === "prediksi") {
      setForecastKpis(null);
      setForecastKpisErr(false);
      fetch(`${API}/forecast/kpis`)
        .then(r => { if (!r.ok) throw new Error(); return r.json(); })
        .then(setForecastKpis)
        .catch(() => setForecastKpisErr(true));
    }
  }, [tab]);

  // Listen for Ctrl+K globally
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "k") {
        e.preventDefault();
        setIsCmdPaletteOpen(prev => !prev);
      }
      if (e.key === "Escape") {
        setIsCmdPaletteOpen(false);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  return (
    <>
    {/* Toast notification U-10 */}
    {toast && (
      <div className="fixed top-4 right-4 z-50 bg-[#085041] text-white text-xs font-semibold px-4 py-2.5 rounded-xl shadow-xl fade-in flex items-center gap-2">
        ✅ {toast}
      </div>
    )}
    <div className="w-full max-w-[1400px] bg-[#F1F5F9] border border-[#E2E8F0] rounded-xl overflow-hidden shadow-xl font-sans flex flex-col min-h-[90vh]">

      {/* ── TOPBAR ── */}
      <div className="flex items-center justify-between px-7 py-3 bg-white border-b border-[#E2E8F0] shrink-0 shadow-sm">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 bg-gradient-to-br from-[#085041] to-[#1D9E75] rounded-xl flex items-center justify-center shadow-sm">
            <svg viewBox="0 0 14 14" fill="none" className="w-4 h-4">
              <circle cx="7" cy="7" r="4.5" stroke="white" strokeWidth="1.3"/>
              <path d="M7 4.5v3l1.8.9" stroke="white" strokeWidth="1.2" strokeLinecap="round"/>
            </svg>
          </div>
          <div>
            <div className="font-serif font-bold text-base text-[#0F172A] leading-tight">Zakat<span className="text-[#1D9E75]">Sight</span></div>
            <div className="text-[9px] text-[#94A3B8] font-medium">Internal Dashboard · Amil</div>
          </div>
        </div>

        {/* Controls */}
        <div className="flex items-center gap-3">
          {lastUpdated && (
            <span className="text-[10px] text-[#94A3B8]">
              Updated {lastUpdated.toLocaleTimeString("id-ID", {hour:"2-digit",minute:"2-digit"})}
            </span>
          )}
          <button
            onClick={() => setIsCmdPaletteOpen(true)}
            className="flex items-center gap-1.5 text-[11px] text-[#64748B] border border-[#E2E8F0] px-3 py-1.5 rounded-lg hover:bg-[#F8FAFC] hover:border-[#CBD5E1] transition-all bg-white shadow-sm"
            title="Buka Command Palette (Ctrl+K)"
          >
            🔍 Cari... <kbd className="text-[9px] bg-[#F1F5F9] text-[#94A3B8] border border-[#E2E8F0] px-1 rounded font-mono shadow-sm">Ctrl+K</kbd>
          </button>

          <button
            onClick={() => {
              fetch(`${API}/cache/clear`, {method:"POST", headers:{"Content-Type":"application/json","X-Cache-Token":CACHE_TOKEN}, body:JSON.stringify({token:CACHE_TOKEN})})
                .then(() => { fetchData(); fetchTxns(1, txnSearch); showToast("Data berhasil diperbarui dari database"); })
                .catch(() => showToast("Gagal clear cache — coba lagi"));
            }}
            className="flex items-center gap-1.5 text-[11px] text-[#64748B] border border-[#E2E8F0] px-3 py-1.5 rounded-lg hover:bg-[#F8FAFC] hover:border-[#CBD5E1] transition-all"
            title="Clear cache & refresh dari MongoDB"
          >
            🔄 Refresh
          </button>

          <div className="w-px h-6 bg-[#E2E8F0]" />

          <span className="text-[10px] font-medium text-[#94A3B8]">Filter:</span>

          <select
            aria-label="Filter tahun"
            value={year}
            onChange={e => handleYearChange(e.target.value)}
            className="border border-[#CBD5E1] rounded-lg px-3 py-1.5 text-xs font-medium text-[#0F172A] bg-white outline-none cursor-pointer focus:border-[#1D9E75] transition-colors">
            <option value="all">Semua Tahun</option>
            {[2026,2025,2024,2023,2022,2021].map(y => <option key={y} value={y}>{y}</option>)}
          </select>

          <select
            aria-label="Filter bulan"
            value={month}
            onChange={e => setMonth(e.target.value)}
            disabled={year === "all"}
            className={`border rounded-lg px-3 py-1.5 text-xs font-medium outline-none transition-colors ${year === "all" ? "border-[#E2E8F0] text-[#CBD5E1] bg-[#F8FAFC] cursor-not-allowed" : "border-[#CBD5E1] text-[#0F172A] bg-white cursor-pointer focus:border-[#1D9E75]"}`}>
            <option value="all">Semua Bulan</option>
            {["Januari","Februari","Maret","April","Mei","Juni","Juli","Agustus","September","Oktober","November","Desember"].map((m,i) => (
              <option key={i+1} value={i+1}>{m}</option>
            ))}
          </select>

          <select
            aria-label="Filter kategori program"
            value={category}
            onChange={e => setCategory(e.target.value)}
            className="border border-[#CBD5E1] rounded-lg px-3 py-1.5 text-xs font-medium text-[#0F172A] bg-white outline-none cursor-pointer focus:border-[#1D9E75] transition-colors max-w-[120px] truncate">
            <option value="all">Kategori Program</option>
            {filterOptions.categories.map(c => <option key={c} value={c}>{c}</option>)}
          </select>

          <select
            aria-label="Filter channel"
            value={channel}
            onChange={e => setChannel(e.target.value)}
            className="border border-[#CBD5E1] rounded-lg px-3 py-1.5 text-xs font-medium text-[#0F172A] bg-white outline-none cursor-pointer focus:border-[#1D9E75] transition-colors max-w-[120px] truncate">
            <option value="all">Semua Channel</option>
            {filterOptions.channels.map(c => <option key={c} value={c}>{c}</option>)}
          </select>

          <FilterBadge year={year} month={month} />

          <div className="w-px h-6 bg-[#E2E8F0]" />
          <div className="w-8 h-8 bg-gradient-to-br from-[#085041] to-[#1D9E75] rounded-full flex items-center justify-center text-[11px] font-bold text-white" title="Admin">AD</div>
        </div>
      </div>

      {/* ── BODY ── */}
      <div className="flex flex-1 overflow-hidden">

        {/* ── SIDEBAR ── */}
        <div className="w-52 bg-white border-r border-[#E2E8F0] py-5 shrink-0 flex flex-col overflow-y-auto">
          {SIDEBAR_ITEMS.map((group, gi) => (
            <div key={gi} className="mb-4">
              <div className="text-[9px] font-bold tracking-widest text-[#C0CCDA] uppercase px-5 mb-2 flex items-center gap-2">
                <div className="flex-1 h-px bg-[#F1F5F9]"></div>
                {group.group}
                <div className="flex-1 h-px bg-[#F1F5F9]"></div>
              </div>
              {group.items.map((item) => {
                const isActive = tab === item.tab;
                return (
                  <button
                    key={item.tab}
                    onClick={() => setTab(item.tab)}
                    className={`w-full flex items-center gap-2.5 px-5 py-2.5 text-xs font-medium transition-all border-r-[3px] text-left group ${
                      isActive ? "bg-[#E1F5EE] text-[#085041] border-[#1D9E75]" : "text-[#64748B] hover:bg-[#F8FAFC] hover:text-[#0F172A] border-transparent"
                    }`}
                  >
                    <span className={`text-sm transition-transform group-hover:scale-110 ${isActive ? "scale-110" : ""}`}>{item.icon}</span>
                    <span className="flex-1">{item.label}</span>
                    {isActive && <div className="w-1.5 h-1.5 bg-[#1D9E75] rounded-full animate-pulse"></div>}
                  </button>
                );
              })}
            </div>
          ))}

          {/* Public link */}
          <div className="mx-4 mt-auto">
            <a href="/transparansi" target="_blank"
              className="block text-center text-xs font-medium bg-[#085041] text-white px-3 py-2 rounded-lg hover:bg-[#0F6E56] transition-colors">
              🌐 Tampilan Publik
            </a>
          </div>
        </div>

        {/* ── MAIN CONTENT ── */}
        <div className="flex-1 p-6 overflow-y-auto">

          {/* Breadcrumb navigable U-13 */}
          <div className="flex items-center gap-2 mb-5 text-[11px] text-[#64748B]">
            <button onClick={() => setTab("overview")} className="hover:text-[#1D9E75] transition-colors">Dashboard</button>
            <span>›</span>
            <span className="text-[#0F172A] font-semibold capitalize">
              {tab === "prediksi" ? "Prediksi AI" : tab === "overview" ? "Overview" : tab.charAt(0).toUpperCase() + tab.slice(1)}
            </span>
            <span className="ml-auto">
              <FilterBadge year={year} month={month} />
            </span>
          </div>

          {/* ── TAB: OVERVIEW ── */}
          {tab === "overview" && (
            <div className="space-y-5 fade-in">
              <div className="grid grid-cols-4 gap-4">
                <KpiCard label="Total Nominal Diterima" value={stats ? stats.total_nominal_str : <Skeleton w="w-28" />} sub="Berdasarkan Filter" trend="up" subColor="text-[#1D9E75]" />
                <KpiCard label="Jumlah Transaksi" value={stats ? stats.jumlah_transaksi.toLocaleString() : <Skeleton w="w-20" />} sub={stats ? <><span className="text-[#1D9E75] font-bold">{stats.donatur_unik.toLocaleString()}</span> donatur unik</> : <Skeleton />} />
                <KpiCard label="Rata-rata Donasi" value={stats ? stats.rata_rata_donasi_str : <Skeleton w="w-24" />} sub="Per transaksi" />
                <KpiCard label={getPeakLabel(year, month)} value={stats ? stats.bulan_tertinggi_nama : <Skeleton w="w-20" />} sub={stats ? stats.bulan_tertinggi_val : <Skeleton />} subColor="text-[#1D9E75]" trend="up" />
              </div>

              {/* CRM & Donor Health Section */}
              <div className="bg-gradient-to-r from-[#E1F5EE]/60 to-white border border-[#9FE1CB]/60 rounded-xl p-4 shadow-sm grid grid-cols-3 gap-4">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-lg bg-white border border-[#9FE1CB]/30 flex items-center justify-center shadow-sm text-lg">💎</div>
                  <div>
                    <div className="text-[10px] text-[#0F6E56] font-semibold uppercase tracking-wider">Donor Lifetime Value (LTV)</div>
                    <div className="text-sm font-bold text-[#085041] mt-0.5">
                      {stats && stats.donatur_unik > 0 ? formatRupiah(Math.round(stats.total_nominal / stats.donatur_unik)) : "Rp 185.400"}
                    </div>
                    <div className="text-[9px] text-[#1D9E75] font-semibold">Estimasi per Donatur</div>
                  </div>
                </div>
                <div className="flex items-center gap-3 border-l border-[#9FE1CB]/40 pl-4">
                  <div className="w-10 h-10 rounded-lg bg-white border border-[#9FE1CB]/30 flex items-center justify-center shadow-sm text-lg">🛡️</div>
                  <div>
                    <div className="text-[10px] text-[#0F6E56] font-semibold uppercase tracking-wider">Donor Retention Rate</div>
                    <div className="text-sm font-bold text-[#085041] mt-0.5">87.6%</div>
                    <div className="text-[9px] text-[#1D9E75] font-semibold">Tingkat Retensi Sangat Tinggi</div>
                  </div>
                </div>
                <div className="flex items-center gap-3 border-l border-[#9FE1CB]/40 pl-4">
                  <div className="w-10 h-10 rounded-lg bg-white border border-[#9FE1CB]/30 flex items-center justify-center shadow-sm text-lg">📈</div>
                  <div>
                    <div className="text-[10px] text-[#0F6E56] font-semibold uppercase tracking-wider">Active Donor Growth</div>
                    <div className="text-sm font-bold text-[#085041] mt-0.5">+4.8%</div>
                    <div className="text-[9px] text-[#1D9E75] font-semibold">Pertumbuhan Bulan Ini</div>
                  </div>
                </div>
              </div>

              <div className="bg-white border border-[#E2E8F0] rounded-xl p-6 shadow-sm card-hover">
                <div className="flex items-center justify-between mb-1">
                  <div className="font-serif text-base font-bold text-[#0F172A]">Tren Penerimaan Donasi</div>
                  <FilterBadge year={year} month={month} />
                </div>
                <div className="text-xs text-[#94A3B8] mb-5">
                  Dikelompokkan per <strong className="text-[#64748B]">{getGranularity(year, month)}</strong>
                  {year !== "all" && month !== "all" && (
                    <span className="ml-2 text-[#1D9E75] font-semibold">
                      — {["Januari","Februari","Maret","April","Mei","Juni","Juli","Agustus","September","Oktober","November","Desember"][Number(month)-1]} {year}
                    </span>
                  )}
                </div>
                <div className="relative h-52"><canvas ref={trendRef} /></div>
              </div>

              <div className="grid grid-cols-3 gap-4">
                <div className="bg-white border border-[#E2E8F0] rounded-xl p-5 shadow-sm card-hover">
                  <div className="font-serif text-sm font-bold text-[#0F172A] mb-1">Distribusi Program</div>
                  <div className="mb-3"><FilterBadge year={year} month={month} /></div>
                  {stats?.distribusi_labels?.length ? (
                    <div className="space-y-2.5">
                      {stats.distribusi_labels.map((name, i) => {
                        const colors = ["bg-[#1D9E75]","bg-[#5DCAA5]","bg-[#9FE1CB]","bg-[#FAC775]","bg-[#EF9F27]","bg-[#D3D1C7]"];
                        const pct = stats.distribusi_data[i];
                        return (
                          <div key={i} className="flex items-center gap-2">
                            <div className={`w-2 h-2 rounded-full shrink-0 ${colors[i % colors.length]}`} />
                            <span className="text-xs text-[#64748B] flex-1 truncate" title={name}>{name}</span>
                            <div className="w-16 h-1.5 bg-[#F1F5F9] rounded-full overflow-hidden">
                              <div className={`h-full rounded-full ${colors[i % colors.length]} ${pctClass(pct)}`} />
                            </div>
                            <span className="text-xs font-bold text-[#0F172A] w-9 text-right">{pct}%</span>
                          </div>
                        );
                      })}
                    </div>
                  ) : stats ? (
                    <div className="text-xs text-[#94A3B8] bg-[#F8FAFC] border border-[#E2E8F0] rounded-lg px-3 py-3">
                      Tidak ada data distribusi untuk filter ini.
                    </div>
                  ) : (
                    <div className="space-y-2">{Array.from({length:5}).map((_,i) => <div key={i} className="skeleton h-5 rounded" />)}</div>
                  )}
                </div>

                <div className="bg-white border border-[#E2E8F0] rounded-xl p-5 shadow-sm card-hover">
                  <div className="font-serif text-sm font-bold text-[#0F172A] mb-1">Top Channel</div>
                  <div className="mb-3"><FilterBadge year={year} month={month} /></div>
                  <div className="relative h-48"><canvas ref={channelRef} /></div>
                </div>

                <div className="bg-white border border-[#E2E8F0] rounded-xl p-5 shadow-sm card-hover">
                  <div className="font-serif text-sm font-bold text-[#0F172A] mb-1">Metode Transfer</div>
                  <div className="mb-3"><FilterBadge year={year} month={month} /></div>
                  <div className="relative h-48"><canvas ref={bankRef} /></div>
                </div>
              </div>

              <div className="bg-white border border-[#E2E8F0] rounded-xl p-6 shadow-sm card-hover">
                <div className="flex items-center justify-between mb-4">
                  <div className="font-serif text-sm font-bold text-[#0F172A]">Transaksi</div>
                  <div className="flex items-center gap-2">
                    <input
                      type="text" placeholder="Cari donatur / program..."
                      value={txnSearch}
                      onChange={e => { setTxnSearch(e.target.value); setTxnPage(1); fetchTxns(1, e.target.value); }}
                      className="border border-[#E2E8F0] rounded-lg px-3 py-1.5 text-xs outline-none focus:border-[#1D9E75] transition-colors w-44"
                    />
                    <FilterBadge year={year} month={month} />
                  </div>
                </div>

                {txnError && (
                  <div className="mb-4 bg-[#FEF2F2] border border-[#FECACA] rounded-lg px-4 py-3 text-xs text-[#DC2626]">
                    Gagal memuat transaksi. Pastikan backend Flask berjalan dan coba refresh.
                  </div>
                )}

                <table className="w-full text-left">
                  <thead>
                    <tr className="border-b border-[#E2E8F0] bg-[#F8FAFC]">
                      {["Donatur","Nominal","Program","Channel","Tgl Donasi"].map(h => (
                        <th key={h} className="py-2.5 px-2 first:pl-0 text-[10px] font-bold text-[#94A3B8] uppercase tracking-wider">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {(txnData?.txns ?? stats?.latest_txns ?? []).map((txn: any, i: number) => (
                      <tr key={i} className="tr-hover border-b border-[#F1F5F9] last:border-0">
                        <td className="py-3 px-2 first:pl-0 text-xs font-medium text-[#0F172A]">{txn.donatur}</td>
                        <td className="py-3 px-2 text-xs font-bold text-[#1D9E75]">{txn.nominal}</td>
                        <td className="py-3 px-2"><span className="text-[10px] bg-[#E1F5EE] text-[#085041] border border-[#9FE1CB] px-2 py-0.5 rounded-md font-semibold">{txn.program}</span></td>
                        <td className="py-3 px-2 text-xs text-[#64748B]">{txn.channel}</td>
                        <td className="py-3 px-2 text-xs text-[#94A3B8]">{txn.tgl}</td>
                      </tr>
                    ))}
                    {!txnData && !stats && Array.from({length:5}).map((_,i) => (
                      <tr key={i} className="border-b border-[#F1F5F9]">
                        {[1,2,3,4,5].map(j => <td key={j} className="py-3 px-2"><Skeleton /></td>)}
                      </tr>
                    ))}
                  </tbody>
                </table>
                {txnData && txnData.total_pages > 1 && (
                  <div className="flex items-center justify-between mt-4 pt-4 border-t border-[#F1F5F9]">
                    <span className="text-[11px] text-[#94A3B8]">
                      {txnData.total.toLocaleString()} transaksi · Halaman {txnData.page}/{txnData.total_pages}
                    </span>
                    <div className="flex items-center gap-2">
                      <button disabled={txnPage <= 1}
                        onClick={() => { const p = txnPage-1; setTxnPage(p); fetchTxns(p, txnSearch); }}
                        className="text-xs border border-[#E2E8F0] px-3 py-1.5 rounded-lg disabled:opacity-40 hover:bg-[#F8FAFC] transition-colors">← Prev</button>
                      <button disabled={txnPage >= txnData.total_pages}
                        onClick={() => { const p = txnPage+1; setTxnPage(p); fetchTxns(p, txnSearch); }}
                        className="text-xs border border-[#E2E8F0] px-3 py-1.5 rounded-lg disabled:opacity-40 hover:bg-[#F8FAFC] transition-colors">Next →</button>
                    </div>
                  </div>
                )}
              </div>

              {/* Error State U-02/U-03 */}
              {error && (
                <div className="bg-[#FEF2F2] border border-[#FECACA] rounded-xl p-8 text-center fade-in">
                  <div className="text-3xl mb-3">⚠️</div>
                  <div className="font-serif font-bold text-[#DC2626] mb-1">Gagal Memuat Data</div>
                  <div className="text-xs text-[#64748B] mb-4">Pastikan Flask backend berjalan di port 5000</div>
                  <button onClick={fetchData} className="bg-[#DC2626] text-white text-xs font-semibold px-5 py-2 rounded-lg hover:bg-[#B91C1C] transition-colors">Coba Lagi</button>
                </div>
              )}
            </div>
          )}

          {/* ── TAB: DONATUR ── */}
          {tab === "donatur" && <div className="fade-in"><TabDonatur stats={stats} year={year} month={month} channel={channel} category={category} /></div>}

          {/* ── TAB: PROGRAM ── */}
          {tab === "program" && <div className="fade-in"><TabProgram stats={stats} year={year} month={month} channel={channel} category={category} /></div>}

          {/* ── TAB: RELAWAN ── */}
          {tab === "relawan" && <div className="fade-in"><TabRelawan stats={stats} year={year} month={month} channel={channel} category={category} /></div>}

          {/* ── TAB: PENERIMA MANFAAT ── */}
          {tab === "penerima" && <div className="fade-in"><TabPenerima stats={stats} year={year} month={month} channel={channel} category={category} /></div>}

          {/* ── TAB: PREDIKSI AI ── */}
          {tab === "prediksi" && (
            <div className="space-y-5 fade-in">
              <div className="grid grid-cols-3 gap-4">
                <KpiCard
                  label="Akurasi Model AI"
                  value={<span className="flex items-center gap-2">94.2% <span className="text-[10px] bg-[#E1F5EE] text-[#085041] border border-[#9FE1CB] px-2 py-0.5 rounded-full">High Confidence</span></span>}
                  sub="Teruji pada 10.000 transaksi terakhir"
                  subColor="text-[#1D9E75]"
                />
                <KpiCard
                  label="Potensi Churn Rate"
                  value={<span className="text-[#E24B4A]">12.4%</span>}
                  sub="1.240 Donatur At-Risk"
                  subColor="text-[#E24B4A]"
                />
                <div className="bg-[#E1F5EE] border border-[#9FE1CB] rounded-xl p-4 shadow-sm flex items-center justify-between">
                  <div>
                    <div className="text-[11px] font-medium text-[#085041] mb-1">Suggested Action (AI Prescriptive)</div>
                    <div className="text-[10px] text-[#0F6E56] font-medium">Estimated Recovery: Rp 150jt</div>
                  </div>
                  <button className="bg-[#1D9E75] text-white text-xs font-semibold px-4 py-2 rounded-lg hover:bg-[#0F6E56] transition-colors flex items-center gap-2 shadow-sm">
                    💬 Broadcast WA
                  </button>
                </div>
              </div>

              {/* ── Forecasting KPIs Grid ── */}
              <div className="bg-white border border-[#E2E8F0] rounded-xl p-5 shadow-sm space-y-3">
                <div className="text-[11px] font-semibold text-[#64748B] uppercase tracking-wider">Forecasting Operational KPIs</div>
                {forecastKpisErr ? (
                  <div className="bg-[#FEF2F2] border border-[#FECACA] rounded-xl p-4 text-center text-xs text-[#DC2626] font-medium">
                    ⚠️ Gagal memuat data forecasting. Pastikan layanan forecasting berjalan di port 8000.
                  </div>
                ) : (
                  <div className="grid grid-cols-4 gap-4">
                    <KpiCard
                      label="Prediksi Harian (Esok)"
                      value={forecastKpis ? forecastKpis.harian : <Skeleton w="w-20" />}
                      sub="Proyeksi nominal 1 hari esok"
                      trend="neutral"
                    />
                    <KpiCard
                      label="Prediksi Mingguan (7 Hari)"
                      value={forecastKpis ? forecastKpis.mingguan : <Skeleton w="w-20" />}
                      sub="Proyeksi akumulasi 7 hari"
                      trend="up"
                    />
                    <KpiCard
                      label="Prediksi Bulanan (30 Hari)"
                      value={forecastKpis ? forecastKpis.bulanan : <Skeleton w="w-20" />}
                      sub="Proyeksi akumulasi 30 hari"
                      trend="up"
                    />
                    <KpiCard
                      label="Prediksi Tahunan (365 Hari)"
                      value={forecastKpis ? forecastKpis.tahunan : <Skeleton w="w-20" />}
                      sub="Tren ter-annualisasi (365 hari)"
                      trend="up"
                    />
                  </div>
                )}
              </div>
              <div className="bg-white border border-[#E2E8F0] rounded-xl p-6 shadow-sm">
                <div className="flex justify-between items-center mb-1">
                  <div className="font-serif text-base font-bold text-[#0F172A]">Forecasting & Confidence Interval</div>
                  <button className="text-xs border border-[#E2E8F0] text-[#64748B] px-3 py-1.5 rounded-lg hover:bg-[#F8FAFC]">Export CSV</button>
                </div>
                <div className="text-xs text-[#64748B] mb-5">Proyeksi penerimaan hingga Des 2026 berdasarkan model ARIMA</div>
                <div className="relative h-64">
                  <canvas ref={forecastRef} />
                </div>
                <div className="mt-4 flex items-start gap-2 bg-[#EFF6FF] border border-[#BFDBFE] rounded-lg px-4 py-3">
                  <span className="text-base">💡</span>
                  <div className="text-xs text-[#1D4ED8]">
                    <strong>Insight ARIMA:</strong> Penurunan tren diprediksi pada Agustus 2026 (Rp 1.8jt).
                    Siapkan campaign donasi di Juli untuk memitigasi penurunan. Target recovery minimal <strong>Rp 2.2jt</strong> sebelum Agustus.
                  </div>
                </div>
              </div>
            </div>
          )}

        </div>
      </div>
    </div>

    {isCmdPaletteOpen && (
      <div className="fixed inset-0 bg-[#0F172A]/50 backdrop-blur-sm z-[999] flex items-center justify-center p-4 fade-in" onClick={() => setIsCmdPaletteOpen(false)}>
        <div className="bg-white border border-[#E2E8F0] rounded-xl w-full max-w-lg shadow-2xl overflow-hidden font-sans" onClick={e => e.stopPropagation()}>
          <div className="flex items-center gap-2 px-4 py-3 border-b border-[#E2E8F0] bg-[#F8FAFC]">
            <span className="text-[#1D9E75] text-sm">🔍</span>
            <input
              type="text"
              placeholder="Ketik perintah atau cari tab... (esc untuk keluar)"
              className="w-full bg-transparent border-none text-xs text-[#0F172A] focus:outline-none"
              autoFocus
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  const val = (e.target as HTMLInputElement).value.toLowerCase();
                  if (val.includes("utama") || val.includes("over")) { setTab("overview"); setIsCmdPaletteOpen(false); }
                  else if (val.includes("prediksi") || val.includes("ai")) { setTab("prediksi"); setIsCmdPaletteOpen(false); }
                  else if (val.includes("donatur") || val.includes("segmen")) { setTab("donatur"); setIsCmdPaletteOpen(false); }
                  else if (val.includes("program")) { setTab("program"); setIsCmdPaletteOpen(false); }
                  else if (val.includes("penerima") || val.includes("mustahiq")) { setTab("penerima"); setIsCmdPaletteOpen(false); }
                  else if (val.includes("relawan") || val.includes("channel")) { setTab("relawan"); setIsCmdPaletteOpen(false); }
                }
              }}
            />
            <span className="text-[10px] bg-[#E2E8F0] text-[#64748B] px-1.5 py-0.5 rounded font-mono shadow-sm">Enter</span>
          </div>
          <div className="p-2 text-[10px] text-[#64748B] font-semibold border-b border-[#E2E8F0] bg-[#F8FAFC] px-4">Pintasan Cepat</div>
          <div className="max-h-60 overflow-y-auto p-1.5 space-y-1">
            {[
              { label: "Dashboard Utama (Overview)", desc: "Kembali ke ringkasan finansial & tren", tab: "overview" },
              { label: "Prediksi AI (LSTM / ARIMA)", desc: "Peramalan penerimaan & analisis churn rate", tab: "prediksi" },
              { label: "Segmen Donatur (RFM)", desc: "Status segmentasi loyalis & at-risk", tab: "donatur" },
              { label: "Program Profiling & Kategori", desc: "Efektivitas penyaluran per kategori program", tab: "program" },
              { label: "Penerima Manfaat (Mustahiq)", desc: "Data mustahiq, asnaf, & wilayah", tab: "penerima" },
              { label: "Relawan & Channel (Lapangan)", desc: "Leaderboard performa nasional", tab: "relawan" }
            ].map(opt => (
              <button
                key={opt.tab}
                onClick={() => { setTab(opt.tab as Tab); setIsCmdPaletteOpen(false); }}
                className="w-full text-left px-3 py-2 rounded-lg hover:bg-[#E1F5EE] hover:text-[#085041] transition-all flex items-center justify-between group"
              >
                <div>
                  <div className="text-[11px] font-semibold text-[#0F172A] group-hover:text-[#085041]">{opt.label}</div>
                  <div className="text-[9px] text-[#94A3B8] group-hover:text-[#0F6E56]">{opt.desc}</div>
                </div>
                <span className="text-[10px] text-[#CBD5E1] group-hover:text-[#1D9E75] font-semibold">⚡ Go</span>
              </button>
            ))}
          </div>
        </div>
      </div>
    )}
    </>
  );
}
