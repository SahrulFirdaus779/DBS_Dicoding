"use client";
import React, { useEffect, useState } from "react";

const API = "/api";
type TabProps = { stats: any; year: string; month: string };

function FilterBadge({ year, month }: { year: string; month: string }) {
  const m = ["","Jan","Feb","Mar","Apr","Mei","Jun","Jul","Ags","Sep","Okt","Nov","Des"];
  const label = year === "all" ? "Semua Waktu" : month === "all" ? `Tahun ${year}` : `${m[Number(month)]} ${year}`;
  return <span className="text-[10px] bg-[#E1F5EE] text-[#085041] border border-[#9FE1CB] px-2 py-0.5 rounded-full font-bold">🗓 {label}</span>;
}
function Skeleton({ w = "w-20" }: { w?: string }) {
  return <span className={`skeleton inline-block ${w} h-4 rounded`} />;
}

// ── TAB DONATUR ────────────────────────────────────────────────
export function TabDonatur({ stats, year, month }: TabProps) {
  const [data, setData] = useState<any>(null);
  const [err, setErr] = useState(false);

  useEffect(() => {
    setData(null); setErr(false);
    fetch(`${API}/analytics/donatur?year=${year}&month=${month}`)
      .then(r => { if (!r.ok) throw new Error(); return r.json(); })
      .then(setData)
      .catch(() => setErr(true));
  }, [year, month]);

  if (err) return (
    <div className="bg-[#FEF2F2] border border-[#FECACA] rounded-xl p-8 text-center fade-in">
      <div className="text-2xl mb-2">⚠️</div>
      <div className="font-semibold text-[#DC2626] mb-1">Gagal memuat data donatur</div>
      <button onClick={() => { setErr(false); setData(null); fetch(`${API}/analytics/donatur`).then(r=>r.json()).then(setData).catch(()=>setErr(true)); }}
        className="mt-2 text-xs bg-[#DC2626] text-white px-4 py-1.5 rounded-lg">Coba Lagi</button>
    </div>
  );

  return (
    <div className="space-y-5 fade-in">
      <div className="flex items-center justify-between">
        <div className="font-serif text-base font-bold text-[#0F172A]">Analitik Donatur</div>
        <FilterBadge year={year} month={month} />
      </div>

      <div className="grid grid-cols-4 gap-4">
        {[
          { label:"Total Donatur Unik", val: data ? data.total_donatur?.toLocaleString() : <Skeleton w="w-16" />, sub:"Terdaftar sepanjang waktu", col:"#1D9E75" },
          { label:"Donatur Aktif (90 hari)", val: data ? data.donatur_aktif_90?.toLocaleString() : <Skeleton w="w-14" />, sub:"Aktif 3 bulan terakhir", col:"#1D9E75" },
          { label:"Rata-rata Frekuensi", val: data ? `${data.avg_freq}x` : <Skeleton />, sub:"Per donatur aktif", col:"#64748B" },
          { label:"Transaksi Filter Ini", val: stats ? stats.jumlah_transaksi?.toLocaleString() : <Skeleton />, sub:<FilterBadge year={year} month={month} />, col:"#64748B" },
        ].map((k,i) => (
          <div key={i} className="kpi-card">
            <div className="text-[10px] font-bold text-[#94A3B8] uppercase tracking-wider mb-2">{k.label}</div>
            <div className="font-serif text-2xl font-bold text-[#0F172A]">{k.val}</div>
            <div className="text-[11px] font-medium mt-2" style={{color:k.col}}>{k.sub}</div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-2 gap-5">
        <div className="bg-white border border-[#E2E8F0] rounded-xl p-6 shadow-sm card-hover">
          <div className="font-serif text-sm font-bold text-[#0F172A] mb-4">Top Donatur — Nominal Tertinggi (All Time)</div>
          {data ? (
            <table className="w-full text-left">
              <thead><tr className="border-b border-[#E2E8F0] bg-[#F8FAFC]">{["#","Nama","Total","Frekuensi"].map(h=><th key={h} className="py-2 px-2 first:pl-0 text-[10px] font-bold text-[#94A3B8] uppercase tracking-wider">{h}</th>)}</tr></thead>
              <tbody>
                {data.top_donatur?.map((d: any, i: number) => (
                  <tr key={i} className="tr-hover border-b border-[#F1F5F9] last:border-0">
                    <td className="py-2.5 px-2 first:pl-0"><span className={`text-[10px] font-bold w-5 h-5 rounded-full inline-flex items-center justify-center ${i<3?"bg-[#085041] text-white":"bg-[#F1F5F9] text-[#64748B]"}`}>{i+1}</span></td>
                    <td className="py-2.5 px-2 text-xs font-medium text-[#0F172A]">{d.nama}</td>
                    <td className="py-2.5 px-2 text-xs font-bold text-[#1D9E75]">{d.total_str}</td>
                    <td className="py-2.5 px-2 text-xs text-[#64748B]">{d.frekuensi}x</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : Array.from({length:7}).map((_,i) => <div key={i} className="skeleton h-8 mb-2 rounded-lg" />)}
        </div>

        <div className="bg-white border border-[#E2E8F0] rounded-xl p-6 shadow-sm card-hover">
          <div className="font-serif text-sm font-bold text-[#0F172A] mb-4">Distribusi Frekuensi Donasi</div>
          {data ? (
            <div className="space-y-3">
              {data.freq_labels?.map((label: string, i: number) => {
                const max = Math.max(...(data.freq_data || [1]));
                const pct = Math.round((data.freq_data[i] / max) * 100);
                return (
                  <div key={i} className="flex items-center gap-3">
                    <span className="text-xs text-[#64748B] w-8 text-right shrink-0">{label}</span>
                    <div className="flex-1 h-2 bg-[#F1F5F9] rounded-full overflow-hidden">
                      <div className="h-full bg-[#1D9E75] rounded-full transition-all duration-500" style={{width:`${pct}%`}} />
                    </div>
                    <span className="text-xs font-bold text-[#0F172A] w-16 text-right">{data.freq_data[i].toLocaleString()} donatur</span>
                  </div>
                );
              })}
            </div>
          ) : Array.from({length:6}).map((_,i) => <div key={i} className="skeleton h-6 mb-3 rounded" />)}
        </div>
      </div>

      <div className="bg-white border border-[#E2E8F0] rounded-xl p-6 shadow-sm">
        <div className="font-serif text-sm font-bold text-[#0F172A] mb-1">Segmentasi RFM — Data Riil</div>
        <div className="text-xs text-[#64748B] mb-4">Berdasarkan frekuensi, nilai, dan recency donasi</div>
        {data?.rfm_segments ? (
          <div className="grid grid-cols-5 gap-3">
            {data.rfm_segments.map((s: any, i: number) => {
              const colors = ["#085041","#1D9E75","#5DCAA5","#F59E0B","#EF4444"];
              return (
                <div key={i} className="text-center p-4 rounded-xl border border-[#E2E8F0] bg-[#F8FAFC]">
                  <div className="font-serif text-2xl font-bold" style={{color: colors[i]}}>{s.count.toLocaleString()}</div>
                  <div className="text-[10px] font-bold text-[#64748B] mt-1">{s.seg}</div>
                  <div className="text-[10px] text-[#94A3B8]">{s.pct}%</div>
                </div>
              );
            })}
          </div>
        ) : <div className="skeleton h-16 rounded-xl" />}
        <div className="flex gap-3 flex-wrap mt-4">
          <button onClick={() => { window.open(`https://wa.me/?text=${encodeURIComponent('Assalamu\'alaikum, kami mengundang Anda untuk kembali berdonasi melalui ZakatSight. Bersama kita bisa membantu lebih banyak mustahiq!')}`, '_blank'); }}
            className="bg-[#25D366] text-white text-xs font-semibold px-5 py-2.5 rounded-lg hover:opacity-90 transition-opacity flex items-center gap-2">
            💬 Broadcast WhatsApp
          </button>
          <button onClick={() => { if(data) { const csv = "Nama,Total,Frekuensi\n" + data.top_donatur?.map((d:any)=>`${d.nama},${d.total_str},${d.frekuensi}x`).join("\n"); const b = new Blob([csv],{type:"text/csv"}); const a = document.createElement("a"); a.href=URL.createObjectURL(b); a.download="top_donatur.csv"; a.click(); }}}
            className="border border-[#E2E8F0] text-[#64748B] text-xs font-medium px-5 py-2.5 rounded-lg hover:bg-[#F8FAFC] transition-colors flex items-center gap-2">
            📋 Export Top Donatur CSV
          </button>
        </div>
      </div>
    </div>
  );
}

// ── TAB PROGRAM ────────────────────────────────────────────────
export function TabProgram({ stats, year, month }: TabProps) {
  const [data, setData] = useState<any>(null);
  const [err, setErr] = useState(false);

  useEffect(() => {
    setData(null); setErr(false);
    fetch(`${API}/analytics/program?year=${year}&month=${month}`)
      .then(r => { if (!r.ok) throw new Error(); return r.json(); })
      .then(setData)
      .catch(() => setErr(true));
  }, [year, month]);

  if (err) return (
    <div className="bg-[#FEF2F2] border border-[#FECACA] rounded-xl p-8 text-center fade-in">
      <div className="text-2xl mb-2">⚠️</div>
      <div className="font-semibold text-[#DC2626]">Gagal memuat data program</div>
      <button onClick={() => { setErr(false); setData(null); fetch(`${API}/analytics/program`).then(r=>r.json()).then(setData).catch(()=>setErr(true)); }}
        className="mt-3 text-xs bg-[#DC2626] text-white px-4 py-1.5 rounded-lg">Coba Lagi</button>
    </div>
  );

  const programs = data?.programs || [];

  return (
    <div className="space-y-5 fade-in">
      <div className="flex items-center justify-between">
        <div className="font-serif text-base font-bold text-[#0F172A]">Performa Program (All Time)</div>
        <FilterBadge year={year} month={month} />
      </div>

      <div className="grid grid-cols-4 gap-4">
        {[
          { label:"Total Program", val: data ? programs.length : <Skeleton />, sub:"Aktif di database" },
          { label:"Program Terbesar", val: programs[0]?.name?.slice(0,15) || <Skeleton w="w-24" />, sub: programs[0]?.pct_total ? `${programs[0].pct_total}% dari total` : "" },
          { label:"Total Transaksi", val: stats ? stats.jumlah_transaksi?.toLocaleString() : <Skeleton />, sub:<FilterBadge year={year} month={month} /> },
          { label:"Rata-rata Per Program", val: data ? `Rp${Math.round((data.total_nominal||0)/(programs.length||1)/1e6)}jt` : <Skeleton />, sub:"Berdasarkan nominal" },
        ].map((k,i) => (
          <div key={i} className="kpi-card">
            <div className="text-[10px] font-bold text-[#94A3B8] uppercase tracking-wider mb-2">{k.label}</div>
            <div className="font-serif text-2xl font-bold text-[#0F172A]">{k.val}</div>
            <div className="text-[11px] text-[#64748B] mt-2">{k.sub}</div>
          </div>
        ))}
      </div>

      <div className="bg-white border border-[#E2E8F0] rounded-xl p-6 shadow-sm card-hover">
        <div className="flex items-center justify-between mb-5">
          <div className="font-serif text-sm font-bold text-[#0F172A]">Peringkat Program — Data Riil dari MongoDB</div>
          <div className="flex items-center gap-2">
            <FilterBadge year={year} month={month} />
            <button onClick={() => { if(data) { const csv = "Rank,Program,Total,Transaksi,%\n" + programs.map((p:any,i:number)=>`${i+1},${p.name},${p.total_str},${p.txn},${p.pct_total}%`).join("\n"); const b = new Blob([csv],{type:"text/csv"}); const a = document.createElement("a"); a.href=URL.createObjectURL(b); a.download="program_analytics.csv"; a.click(); }}}
              className="text-xs border border-[#E2E8F0] text-[#64748B] px-3 py-1.5 rounded-lg hover:bg-[#F8FAFC] transition-colors">
              📋 Export
            </button>
          </div>
        </div>
        {data ? (
          <div className="space-y-4">
            {programs.map((p: any, i: number) => (
              <div key={i} className="flex items-center gap-3 group">
                <span className={`text-[10px] font-bold w-5 h-5 rounded-full inline-flex items-center justify-center shrink-0 ${i<3?"bg-[#085041] text-white":"bg-[#F1F5F9] text-[#64748B]"}`}>{i+1}</span>
                <span className="text-xs font-medium text-[#0F172A] w-44 shrink-0 truncate" title={p.name}>{p.name}</span>
                <div className="flex-1 h-2 bg-[#F1F5F9] rounded-full overflow-hidden">
                  <div className="h-full bg-[#1D9E75] rounded-full transition-all duration-700 group-hover:bg-[#085041]" style={{width:`${p.pct_max}%`}} />
                </div>
                <span className="text-xs font-bold text-[#1D9E75] w-16 text-right">{p.total_str}</span>
                <span className="text-[10px] text-[#94A3B8] w-14 text-right">{p.txn.toLocaleString()} txn</span>
                <span className="text-[10px] font-bold text-[#64748B] w-10 text-right">{p.pct_total}%</span>
              </div>
            ))}
          </div>
        ) : (
          <div className="space-y-4">
            {Array.from({length:8}).map((_,i) => <div key={i} className="skeleton h-6 rounded-lg" />)}
          </div>
        )}
      </div>
    </div>
  );
}

// ── TAB RELAWAN ────────────────────────────────────────────────
export function TabRelawan({ stats, year, month }: TabProps) {
  const [data, setData] = useState<any>(null);
  const [err, setErr] = useState(false);

  useEffect(() => {
    setData(null); setErr(false);
    fetch(`${API}/analytics/relawan?year=${year}&month=${month}`)
      .then(r => { if (!r.ok) throw new Error(); return r.json(); })
      .then(setData)
      .catch(() => setErr(true));
  }, [year, month]);

  if (err) return (
    <div className="bg-[#FEF2F2] border border-[#FECACA] rounded-xl p-8 text-center fade-in">
      <div className="text-2xl mb-2">⚠️</div>
      <div className="font-semibold text-[#DC2626]">Gagal memuat data relawan</div>
      <button onClick={() => { setErr(false); setData(null); fetch(`${API}/analytics/relawan`).then(r=>r.json()).then(setData).catch(()=>setErr(true)); }}
        className="mt-3 text-xs bg-[#DC2626] text-white px-4 py-1.5 rounded-lg">Coba Lagi</button>
    </div>
  );

  const boards = data?.leaderboard || [];
  const top = boards[0];

  return (
    <div className="space-y-5 fade-in">
      <div className="flex items-center justify-between">
        <div className="font-serif text-base font-bold text-[#0F172A]">Channel Donasi</div>
        <FilterBadge year={year} month={month} />
      </div>

      <div className="grid grid-cols-4 gap-4">
        {[
          { label:"Total Channel Aktif", val: data ? data.total_channel : <Skeleton />, sub:"Di semua wilayah", col:"#1D9E75" },
          { label:"Channel Terbaik", val: top?.nama || <Skeleton w="w-24" />, sub: top?.total_str || "", col:"#1D9E75" },
          { label:"Channel Terbaik (Txn)", val: top?.txn?.toLocaleString() || <Skeleton />, sub:"Jumlah transaksi", col:"#64748B" },
          { label:"Total Transaksi", val: stats ? stats.jumlah_transaksi?.toLocaleString() : <Skeleton />, sub:<FilterBadge year={year} month={month} />, col:"#64748B" },
        ].map((k,i) => (
          <div key={i} className="kpi-card">
            <div className="text-[10px] font-bold text-[#94A3B8] uppercase tracking-wider mb-2">{k.label}</div>
            <div className="font-serif text-2xl font-bold text-[#0F172A]">{k.val}</div>
            <div className="text-[11px] font-medium mt-2" style={{color:k.col}}>{k.sub}</div>
          </div>
        ))}
      </div>

      <div className="bg-white border border-[#E2E8F0] rounded-xl p-6 shadow-sm card-hover">
        <div className="flex justify-between items-center mb-5">
          <div className="font-serif text-sm font-bold text-[#0F172A]">🏆 Leaderboard Channel — Data Riil MongoDB</div>
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-1.5 text-[10px] text-[#94A3B8]">
              <div className="w-2 h-2 bg-[#1D9E75] rounded-full animate-pulse"></div>
              Live data
            </div>
            <button onClick={() => { if(data) { const csv = "Rank,Channel,Total,Transaksi,%\n" + boards.map((r:any)=>`${r.rank},${r.nama},${r.total_str},${r.txn},${r.pct}%`).join("\n"); const b = new Blob([csv],{type:"text/csv"}); const a = document.createElement("a"); a.href=URL.createObjectURL(b); a.download="leaderboard_channel.csv"; a.click(); }}}
              className="text-xs border border-[#E2E8F0] text-[#64748B] px-3 py-1.5 rounded-lg hover:bg-[#F8FAFC] transition-colors">
              📋 Export CSV
            </button>
          </div>
        </div>
        {data ? (
          <table className="w-full text-left">
            <thead>
              <tr className="border-b border-[#E2E8F0] bg-[#F8FAFC]">
                {["#","Nama Channel","Total Nominal","Transaksi","% dari Total","Bar"].map(h => (
                  <th key={h} className="py-2.5 px-2 first:pl-0 text-[10px] font-bold text-[#94A3B8] uppercase tracking-wider">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {boards.map((r: any, i: number) => (
                <tr key={i} className="tr-hover border-b border-[#F1F5F9] last:border-0">
                  <td className="py-3 px-2 first:pl-0">
                    <span className={`text-[10px] font-bold w-5 h-5 rounded-full inline-flex items-center justify-center ${r.rank<=3?"bg-[#085041] text-white":"bg-[#F1F5F9] text-[#64748B]"}`}>{r.rank}</span>
                  </td>
                  <td className="py-3 px-2 text-xs font-semibold text-[#0F172A]">{r.nama}</td>
                  <td className="py-3 px-2 text-xs font-bold text-[#1D9E75]">{r.total_str}</td>
                  <td className="py-3 px-2 text-xs text-[#64748B]">{r.txn.toLocaleString()}</td>
                  <td className="py-3 px-2 text-xs font-semibold text-[#0F172A]">{r.pct}%</td>
                  <td className="py-3 px-2 w-32">
                    <div className="h-1.5 bg-[#F1F5F9] rounded-full overflow-hidden">
                      <div className="h-full bg-[#1D9E75] rounded-full" style={{width:`${r.pct * (100 / (boards[0]?.pct || 1))}%`}} />
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div className="space-y-3">
            {Array.from({length:8}).map((_,i) => <div key={i} className="skeleton h-10 rounded-lg" />)}
          </div>
        )}
      </div>
    </div>
  );
}
