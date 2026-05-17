"use client";

import React, { useEffect, useState, useRef } from "react";
import Chart from "chart.js/auto";

const API = "/api";

function SkeletonText({ w = "w-24", h = "h-5" }: { w?: string; h?: string }) {
  return <span className={`skeleton inline-block rounded ${w} ${h} align-middle`} />;
}

export default function PublicDashboard() {
  const [stats, setStats] = useState<any>(null);
  const [loaded, setLoaded] = useState(false);
  const distChartRef = useRef<HTMLCanvasElement>(null);
  const distChartInstance = useRef<any>(null);

  useEffect(() => {
    fetch(`${API}/v1/public/stats`)
      .then((r) => r.json())
      .then((data) => {
        setStats(data);
        setLoaded(true);
        if (distChartRef.current) {
          if (distChartInstance.current) distChartInstance.current.destroy();
          distChartInstance.current = new Chart(distChartRef.current, {
            type: "bar",
            data: {
              labels: data.distribusi_labels,
              datasets: [{
                data: data.distribusi_data,
                backgroundColor: ["#1D9E75","#5DCAA5","#9FE1CB","#F59E0B","#3B82F6","#8B5CF6"],
                borderRadius: 5,
              }],
            },
            options: {
              indexAxis: "y", responsive: true, maintainAspectRatio: false,
              plugins: { legend: { display: false }, tooltip: { callbacks: { label: (v: any) => `${v.raw}% dari total` } } },
              scales: { x: { grid: { display: false }, ticks: { font: { size: 11 } } }, y: { grid: { color: "rgba(0,0,0,0.04)" }, ticks: { font: { size: 12 } } } },
            },
          });
        }
      })
      .catch(console.error);
  }, []);

  return (
    <div className="w-full max-w-[1400px] bg-white border border-[#E2E8F0] rounded-xl overflow-hidden shadow-xl font-sans">

      {/* ── NAVBAR ── */}
      <nav className="flex justify-between items-center px-8 py-4 bg-white border-b border-[#E2E8F0]">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 bg-[#085041] rounded-lg flex items-center justify-center">
            <svg viewBox="0 0 14 14" fill="none" className="w-4 h-4">
              <circle cx="7" cy="7" r="4.5" stroke="white" strokeWidth="1.3"/>
              <path d="M7 4.5v3l1.8.9" stroke="white" strokeWidth="1.2" strokeLinecap="round"/>
            </svg>
          </div>
          <span className="font-serif font-bold text-lg text-[#0F172A]">Zakat<span className="text-[#1D9E75]">Sight</span></span>
        </div>
        <div className="flex gap-6 text-sm">
          <a href="/" className="text-[#64748B] hover:text-[#1D9E75] transition-colors">Dashboard Amil</a>
          <a href="#program" className="text-[#64748B] hover:text-[#1D9E75] transition-colors">Program</a>
          <a href="#transparansi" className="text-[#1D9E75] font-semibold">Transparansi</a>
          <a href="#tentang" className="text-[#64748B] hover:text-[#1D9E75] transition-colors">Tentang Kami</a>
        </div>
        <button className="bg-[#1D9E75] text-white text-sm font-medium px-5 py-2 rounded-lg hover:bg-[#0F6E56] transition-colors">Donasi Sekarang</button>
      </nav>

      {/* ── HERO ── */}
      <section className="bg-[#085041] px-12 py-14 grid grid-cols-2 gap-12 items-center">
        <div>
          <div className="inline-flex items-center gap-2 bg-[rgba(29,158,117,0.3)] text-[#9FE1CB] text-xs font-medium px-3 py-1.5 rounded-full border border-[rgba(159,225,203,0.3)] mb-5">
            <span className="w-1.5 h-1.5 bg-[#1D9E75] rounded-full"></span>
            Platform Analitik Zakat berbasis AI
          </div>
          <h1 className="font-serif text-4xl font-bold leading-tight text-white mb-5">
            Zakat yang sampai ke tangan{" "}
            <em className="not-italic text-[#5DCAA5]">yang benar-benar membutuhkan</em>
          </h1>
          <p className="text-white/65 text-sm leading-relaxed mb-7 max-w-md">
            ZakatSight menutup gap transparansi dengan teknologi pencatatan real-time yang dapat diaudit secara independen oleh publik.
          </p>
          <div className="flex gap-3 mb-8">
            <button className="bg-[#1D9E75] text-white text-sm font-medium px-5 py-2.5 rounded-lg">Donasi Sekarang</button>
            <button className="border border-[rgba(159,225,203,0.5)] text-[#9FE1CB] text-sm font-medium px-5 py-2.5 rounded-lg">Lihat Dampak Nyata</button>
          </div>
          <div className="flex items-center gap-3">
            <div className="flex">
              {["SR","AF","DK"].map((av,i) => (
                <div key={i} className={`w-6 h-6 rounded-full border-2 border-[#085041] flex items-center justify-center text-[9px] font-bold ${i===0?"bg-[#1D9E75]":i===1?"bg-[#5DCAA5]":"bg-[#9FE1CB] text-[#085041]"} text-white ${i>0?"-ml-1.5":""}`}>{av}</div>
              ))}
            </div>
            <span className="text-white/50 text-xs">4.218 donatur telah mempercayai ZakatSight</span>
          </div>
        </div>
        <div className="bg-white/5 border border-white/10 rounded-xl p-6">
          <div className="text-xs text-white/45 font-medium mb-5">Statistik real-time — terhimpun dari MongoDB</div>
          <div className="grid grid-cols-2 gap-3">
            {[
              { id: "el-terkumpul", label: "Dana terhimpun", val: stats?.total_terkumpul_str },
              { label: "Akurasi AI", val: "94.2%" },
              { id: "el-keluarga", label: "Keluarga terbantu", val: stats?.keluarga_terbantu },
              { id: "el-titik", label: "Titik penyaluran", val: stats ? `${stats.titik_wilayah} titik` : null },
            ].map((item, i) => (
              <div key={i} className="bg-white/5 rounded-lg p-3.5">
                <div className="text-base font-bold text-white">{item.val ?? <SkeletonText w="w-20" />}</div>
                <div className="text-[10px] text-white/45 mt-1">{item.label}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── PROOF STRIP ── */}
      <div className="bg-[#E1F5EE] border-b border-[#9FE1CB] px-12 py-4 flex justify-around">
        {[
          { num: "Rp 327T", label: "Potensi zakat nasional / tahun" },
          { num: "280rb+", label: "Data transaksi teranalisis" },
          { num: "170", label: "LAZ berizin di Indonesia" },
          { num: "68.2%", label: "Pertumbuhan ZIS semester I" },
        ].map((item, i) => (
          <div key={i} className="text-center">
            <div className="font-serif text-2xl font-bold text-[#085041]">{item.num}</div>
            <div className="text-xs text-[#0F6E56] mt-1">{item.label}</div>
          </div>
        ))}
      </div>

      {/* ── DAMPAK ── */}
      <section id="transparansi" className="bg-[#F8FAFC] px-12 py-14">
        <div className="text-center mb-10">
          <div className="text-[11px] font-bold tracking-widest text-[#1D9E75] uppercase mb-2">Dampak Terverifikasi</div>
          <h2 className="font-serif text-3xl font-bold text-[#0F172A]">Bukan sekadar janji — ini datanya</h2>
          <p className="text-sm text-[#64748B] mt-3 max-w-md mx-auto">Setiap rupiah yang masuk dicatat, dianalisis, dan dapat diaudit secara independen.</p>
        </div>

        <div className="grid grid-cols-2 gap-6 mb-6">
          <div className="bg-white border border-[#E2E8F0] rounded-xl p-7 shadow-sm">
            <div className="font-serif text-4xl font-bold text-[#1D9E75] mb-2">
              {stats ? stats.total_disalurkan_str : <SkeletonText w="w-36" h="h-9" />}
            </div>
            <div className="text-xs text-[#64748B] mb-5">Total donasi tersalurkan real-time</div>
            <div className="h-2 w-full bg-[#E2E8F0] rounded-full overflow-hidden mb-2">
              <div className="h-full bg-[#1D9E75] transition-all duration-1000 ease-out rounded-full" style={{ width: loaded ? `${stats.progress_percent}%` : "0%" }}></div>
            </div>
            <div className="flex justify-between text-[10px] text-[#64748B]">
              <span>0%</span>
              <span>{stats ? `${stats.progress_percent}% dari total penerimaan` : <SkeletonText w="w-28" />}</span>
              <span>{stats ? stats.total_terkumpul_str : ""}</span>
            </div>
            <div className="mt-5 flex items-center gap-2 bg-[#E1F5EE] rounded-lg px-3 py-2.5">
              <svg className="w-4 h-4 text-[#085041] shrink-0" viewBox="0 0 14 14" fill="none"><path d="M5 7l2 2 4-3" stroke="#085041" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/><circle cx="7" cy="7" r="5.5" stroke="#085041" strokeWidth="1.2"/></svg>
              <span className="text-xs text-[#085041]">Data diverifikasi dari MongoDB — tidak ada yang disembunyikan</span>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            {[
              { id:"keluarga", label: "Keluarga penerima manfaat", val: stats?.keluarga_terbantu, color: "#1D9E75" },
              { label: "Program aktif", val: stats?.program_aktif, color: "#085041" },
              { id:"titik", label: "Titik wilayah penyaluran", val: stats?.titik_wilayah, color: "#0F172A" },
              { label: "Dana tepat sasaran", val: "98.7%", color: "#1D9E75" },
            ].map((item, i) => (
              <div key={i} className="bg-white border border-[#E2E8F0] rounded-xl p-5 shadow-sm">
                <div className="font-serif text-2xl font-bold" style={{color: item.color}}>
                  {item.val != null ? item.val : <SkeletonText w="w-16" />}
                </div>
                <div className="text-xs text-[#64748B] mt-2">{item.label}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Chart + Table */}
        <div className="grid grid-cols-[1fr_1.4fr] gap-6">
          <div className="bg-white border border-[#E2E8F0] rounded-xl p-6 shadow-sm">
            <h3 className="font-semibold text-sm text-[#0F172A] mb-1">Distribusi Penyaluran Dana (Asnaf)</h3>
            <p className="text-xs text-[#64748B] mb-4">Berdasarkan kategori penerima zakat</p>
            <div className="relative h-[240px] w-full">
              <canvas ref={distChartRef}></canvas>
            </div>
          </div>
          <div className="bg-white border border-[#E2E8F0] rounded-xl p-6 shadow-sm">
            <h3 className="font-semibold text-sm text-[#0F172A] mb-4">Live: Penerimaan Terbaru</h3>
            <table className="w-full text-left">
              <thead>
                <tr className="border-b border-[#E2E8F0]">
                  {["Donatur","Program","Nominal","Waktu"].map(h => (
                    <th key={h} className="pb-3 text-[11px] font-semibold text-[#64748B]">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {stats ? stats.latest_donations.map((txn: any, i: number) => (
                  <tr key={i} className="border-b border-[#E2E8F0] last:border-0">
                    <td className="py-3">
                      <span className="inline-flex items-center gap-1.5 bg-[#E1F5EE] text-[#085041] text-[10px] font-medium px-2 py-1 rounded-md">
                        🔒 {txn.donatur}
                      </span>
                    </td>
                    <td className="py-3 text-xs text-[#64748B]">{txn.program}</td>
                    <td className="py-3 text-xs font-bold text-[#1D9E75]">{txn.nominal}</td>
                    <td className="py-3 text-xs text-[#64748B]">{txn.waktu}</td>
                  </tr>
                )) : (
                  Array.from({length:5}).map((_,i) => (
                    <tr key={i} className="border-b border-[#E2E8F0]">
                      {[1,2,3,4].map(j => <td key={j} className="py-3"><SkeletonText w="w-full" /></td>)}
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      {/* ── CARA KERJA ── */}
      <section className="bg-[#085041] px-12 py-14">
        <div className="text-center mb-10">
          <div className="text-[11px] font-bold tracking-widest text-[#9FE1CB] uppercase mb-2">Cara Kerja</div>
          <h2 className="font-serif text-3xl font-bold text-white">Dari donasi Anda ke tangan penerima</h2>
        </div>
        <div className="grid grid-cols-4 gap-5">
          {[
            { num:"01", title:"Donasi masuk", desc:"Dana diterima dan dicatat otomatis ke sistem secara real-time" },
            { num:"02", title:"Verifikasi AI", desc:"Model AI menganalisis penerima dan mencocokkan kriteria asnaf" },
            { num:"03", title:"Penyaluran tepat", desc:"Dana disalurkan ke penerima yang tervalidasi, bukan asumsi" },
            { num:"04", title:"Laporan publik", desc:"Donatur mendapat laporan dampak yang bisa diaudit independen" },
          ].map((step, i) => (
            <div key={i} className="bg-white/5 border border-white/10 rounded-xl p-6 text-center">
              <div className="font-serif text-4xl font-bold text-[rgba(159,225,203,0.25)] mb-4">{step.num}</div>
              <div className="w-10 h-10 bg-[rgba(29,158,117,0.3)] rounded-xl mx-auto mb-3 flex items-center justify-center">
                <div className="w-2 h-2 bg-[#9FE1CB] rounded-full"></div>
              </div>
              <div className="text-sm font-semibold text-white mb-2">{step.title}</div>
              <div className="text-xs text-white/50 leading-relaxed">{step.desc}</div>
            </div>
          ))}
        </div>
      </section>

      {/* ── DONASI CTA ── */}
      <section className="bg-[#085041] border-t border-[rgba(255,255,255,0.08)] px-12 py-16">
        <div className="max-w-lg mx-auto text-center">
          <div className="text-[11px] font-bold tracking-widest text-[#9FE1CB] uppercase mb-3">Donasi Sekarang</div>
          <h2 className="font-serif text-3xl font-bold text-white mb-4 leading-snug">Satu langkah kecil dari Anda, perubahan besar bagi mereka</h2>
          <p className="text-sm text-white/60 mb-8">Donasi Anda terlacak, transparan, dan dipastikan sampai ke tangan yang tepat.</p>
          <div className="flex flex-wrap gap-2 justify-center mb-4">
            {["Rp 25rb","Rp 50rb","Rp 100rb","Rp 250rb","Rp 500rb"].map((amt, i) => (
              <button key={i} className={`px-4 py-2 rounded-lg text-sm font-medium border transition-colors ${i===2 ? "bg-white text-[#085041] border-white" : "border-white/25 text-white bg-white/8 hover:bg-white/15"}`}>{amt}</button>
            ))}
          </div>
          <div className="flex gap-2 mb-5">
            <input placeholder="Atau masukkan nominal lain (Rp)..." className="flex-1 bg-white/8 border border-white/20 rounded-lg px-4 py-2.5 text-sm text-white placeholder-white/35 outline-none focus:border-[#1D9E75]" />
            <button className="bg-[#1D9E75] text-white px-5 py-2.5 rounded-lg text-sm font-medium whitespace-nowrap hover:bg-[#0F6E56] transition-colors">Donasi Sekarang</button>
          </div>
          <div className="flex items-center justify-center gap-6 text-xs text-white/45">
            <span>🔒 Transaksi aman & terenkripsi</span>
            <span>✅ Tersalurkan dalam 24 jam</span>
            <span>📋 Bukti penyaluran dapat diaudit</span>
          </div>
        </div>
      </section>

      {/* ── FOOTER ── */}
      <footer className="bg-[#04342C] px-12 py-10">
        <div className="grid grid-cols-4 gap-8 mb-8">
          <div>
            <div className="font-serif text-lg font-bold text-white mb-3">Zakat<span className="text-[#5DCAA5]">Sight</span></div>
            <p className="text-xs text-white/45 leading-relaxed">Platform analitik berbasis AI untuk transparansi dan penyaluran zakat tepat sasaran. Bagian dari Coding Camp 2026 powered by DBS Foundation.</p>
          </div>
          {[
            { title:"Platform", links:["Dashboard Analitik","Model Prediksi AI","Laporan Publik","API Terbuka"] },
            { title:"Program", links:["Pendidikan","Kesehatan","Sosial & Pangan","Penerima Manfaat"] },
            { title:"Tentang", links:["Tim Kami","Coding Camp 2026","DBS Foundation","Hubungi Kami"] },
          ].map((col, i) => (
            <div key={i}>
              <div className="text-[10px] font-bold text-white/35 uppercase tracking-widest mb-3">{col.title}</div>
              <div className="flex flex-col gap-2">
                {col.links.map(l => <a key={l} href="#" className="text-xs text-white/55 hover:text-white transition-colors">{l}</a>)}
              </div>
            </div>
          ))}
        </div>
        <div className="border-t border-white/10 pt-5 flex justify-between items-center">
          <div className="text-[10px] text-white/30">© 2026 ZakatSight · CC26-PSU193 · Inclusive & Resilient Communities</div>
          <div className="flex gap-2">
            {["React.js","TensorFlow","FastAPI"].map(t => (
              <span key={t} className="text-[9px] px-2 py-1 bg-white/8 border border-white/10 text-white/40 rounded">{t}</span>
            ))}
          </div>
        </div>
      </footer>
    </div>
  );
}
