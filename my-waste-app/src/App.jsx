import React, { useState, useEffect } from 'react';
import { 
  Cpu, 
  Activity, 
  Eye, 
  Zap, 
  Scale, 
  Camera, 
  CheckCircle2, 
  AlertCircle, 
  Loader2, 
  QrCode,
  ArrowRight
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

const API_BASE = "http://127.0.0.1:8000";

const App = () => {
  const [step, setStep] = useState(0); 
  const [countdown, setCountdown] = useState(10);
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState({ arduino: false, server: false });
  const [data, setData] = useState({
    baseWeight: 0,
    capturedImage: null,
    classification: null,
    wasteType: null,
    result: null
  });
  const [error, setError] = useState(null);

  // Status check
  useEffect(() => {
    const checkStatus = async () => {
      try {
        const res = await fetch(`${API_BASE}/status`);
        const d = await res.json();
        setStatus({ arduino: d.arduino_connected, server: true });
      } catch (e) {
        setStatus({ arduino: false, server: false });
      }
    };
    checkStatus();
    const interval = setInterval(checkStatus, 5000);
    return () => clearInterval(interval);
  }, []);

  // Timer
  useEffect(() => {
    let timer;
    if (step === 2 && countdown > 0) {
      timer = setInterval(() => setCountdown(p => p - 1), 1000);
    } else if (step === 2 && countdown === 0) {
      executeCapture();
    }
    return () => clearInterval(timer);
  }, [step, countdown]);

  const reset = () => {
    setStep(0);
    setCountdown(10);
    setData({ baseWeight: 0, capturedImage: null, classification: null, wasteType: null, result: null });
    setError(null);
  };

  const startProcess = async () => {
    setLoading(true);
    setError(null);
    try {
      setStep(1); // Calibration
      const res = await fetch(`${API_BASE}/measure-base`, { method: 'POST' });
      if (!res.ok) throw new Error("Calibration failed");
      const result = await res.json();
      setData(prev => ({ ...prev, baseWeight: result.weight }));
      
      setLoading(false);
      setStep(2); // Camera Prep
    } catch (e) {
      setError("System Error: Check connections");
      setLoading(false);
      setStep(0);
    }
  };

  const executeCapture = async () => {
    setLoading(true);
    setStep(3); // Analysis
    try {
      const res = await fetch(`${API_BASE}/capture`, { method: 'POST' });
      if (!res.ok) throw new Error("Capture failed");
      const result = await res.json();
      setData(prev => ({ ...prev, capturedImage: result.image }));

      const classRes = await fetch(`${API_BASE}/classify`, { method: 'POST' });
      if (!classRes.ok) throw new Error("AI Classification failed");
      const classData = await classRes.json();
      setData(prev => ({ ...prev, classification: classData.category, wasteType: classData.type }));

      setStep(4); // Sorting
      const sortRes = await fetch(`${API_BASE}/process-waste`, { 
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ type: classData.type })
      });
      if (!sortRes.ok) throw new Error("Sorting Hardware failed");
      const sortResult = await sortRes.json();
      setData(prev => ({ ...prev, result: sortResult }));
      
      setStep(5); // Result
    } catch (e) {
      setError(e.message);
      setStep(0);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#050505] text-white font-sans overflow-hidden selection:bg-blue-500/30">
      
      {/* Header */}
      <nav className="border-b border-white/10 px-8 py-5 flex justify-between items-center bg-[#0a0a0c]">
        <div className="flex flex-col">
          <div className="flex items-center gap-3">
            <div className="bg-blue-600 p-1.5 rounded-lg">
              <Zap size={18} className="text-white" fill="currentColor" />
            </div>
            <h1 className="text-xl font-bold tracking-wide">
              SMART<span className="text-blue-500">RECYCLE</span>
            </h1>
          </div>
          <p className="text-[10px] text-slate-500 font-mono tracking-[0.2em] mt-1 ml-10">ENTERPRISE AI NODE</p>
        </div>

        <div className="flex items-center gap-6">
           <div className="flex flex-col items-end">
             <p className="text-[10px] text-slate-500 font-bold tracking-widest uppercase">System Latency</p>
             <p className="text-emerald-500 font-mono text-xs">14ms</p>
           </div>
           
           <div className={`flex items-center gap-3 px-4 py-2 rounded-full border ${status.arduino ? 'bg-emerald-500/10 border-emerald-500/50' : 'bg-red-500/10 border-red-500/50'}`}>
             <div className={`w-2 h-2 rounded-full ${status.arduino ? 'bg-emerald-500 animate-pulse' : 'bg-red-500'}`} />
             <span className={`text-xs font-bold tracking-widest ${status.arduino ? 'text-emerald-500' : 'text-red-500'}`}>
               {status.arduino ? 'SYSTEM READY' : 'OFFLINE'}
             </span>
           </div>
        </div>
      </nav>

      <main className="grid grid-cols-12 h-[calc(100vh-84px)] p-6 gap-6">
        
        {/* Left Control Panel */}
        <div className="col-span-4 flex flex-col justify-between p-6 bg-[#0a0a0c] rounded-3xl border border-white/5 relative overflow-hidden group">
          {/* Decor */}
          <div className="absolute top-0 right-0 w-64 h-64 bg-blue-600/5 rounded-full blur-3xl -translate-y-1/2 translate-x-1/2" />
          
          <div className="relative z-10">
            <div className="flex items-center justify-between mb-8">
               <h2 className="text-4xl font-bold leading-none">
                 VISION <br/>
                 <span className="text-blue-500">SORTING</span>
               </h2>
               <Cpu size={48} className="text-slate-700" strokeWidth={1} />
            </div>
            
            <p className="text-slate-400 text-sm leading-relaxed max-w-xs mb-10">
              Next-gen neural processing for sustainable waste management. Automated classification and sorting pipeline active.
            </p>

            <button 
              onClick={step === 5 ? reset : startProcess}
              disabled={loading || !status.arduino || (step > 0 && step < 5)}
              className="w-full py-4 bg-blue-600 hover:bg-blue-500 disabled:bg-slate-800 disabled:text-slate-500 text-white rounded-xl font-bold tracking-wide transition-all shadow-lg shadow-blue-900/20 flex items-center justify-center gap-2 group/btn"
            >
              {loading ? <Loader2 className="animate-spin" /> : (
                step === 5 ? "RESET SYSTEM" : "START SYSTEM"
              )}
              {!loading && <ArrowRight size={18} className="group-hover/btn:translate-x-1 transition-transform" />}
            </button>
          </div>

          {/* Phase List */}
          <div className="space-y-4 relative z-10">
            <PhaseItem active={step >= 1} label="Weight Calibration" sub="Tare Scale" icon={Scale} step={1} />
            <PhaseItem active={step >= 3} label="Object Recognition" sub="Gemini Vision Pro" icon={Eye} step={3} />
            <PhaseItem active={step >= 4} label="Automated Sorting" sub="Servo Actuation" icon={Cpu} step={4} />
          </div>
          
          {error && (
             <div className="absolute bottom-6 left-6 right-6 bg-red-500/10 border border-red-500/20 p-3 rounded-lg flex items-center gap-3 text-red-500 text-xs font-mono">
               <AlertCircle size={14} />
               {error}
             </div>
          )}
        </div>

        {/* Right Visualization Panel */}
        <div className="col-span-8 bg-[#0a0a0c] rounded-3xl border border-white/5 relative overflow-hidden flex flex-col">
           {/* Monitor Header */}
           <div className="flex justify-between items-center p-8 border-b border-white/5">
              <div className="flex gap-2">
                <div className="w-1 h-4 bg-blue-600 rounded-full" />
                <h3 className="font-mono text-xs text-slate-500 tracking-widest uppercase">Primary Visual Feed</h3>
              </div>
              <div className="flex gap-8">
                 <Stat label="TEMP" value="24°C" />
                 <Stat label="LOAD" value={loading ? "84%" : "12%"} />
              </div>
           </div>
          
           {/* Main Display Area */}
           <div className="flex-1 relative flex items-center justify-center p-4">
             {/* Corner brackets */}
             <div className="absolute top-8 left-8 w-8 h-8 border-t-2 border-l-2 border-slate-700 rounded-tl-lg" />
             <div className="absolute top-8 right-8 w-8 h-8 border-t-2 border-r-2 border-slate-700 rounded-tr-lg" />
             <div className="absolute bottom-8 left-8 w-8 h-8 border-b-2 border-l-2 border-slate-700 rounded-bl-lg" />
             <div className="absolute bottom-8 right-8 w-8 h-8 border-b-2 border-r-2 border-slate-700 rounded-br-lg" />

             <AnimatePresence mode="wait">
               {step === 0 && (
                 <motion.div 
                   key="idle"
                   initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                   className="text-center"
                 >
                   <Eye size={64} className="text-slate-800 mx-auto mb-6 animate-pulse" />
                   <h3 className="text-slate-700 font-mono tracking-[0.3em] text-sm uppercase">Visual Sensors Active</h3>
                 </motion.div>
               )}

               {step === 2 && (
                 <motion.div key="countdown" className="text-9xl font-black text-white">{countdown}</motion.div>
               )}

               {(step === 3 || step === 4) && (
                 <motion.div key="processing" className="relative w-full h-full flex flex-col items-center justify-center">
                    {data.capturedImage && (
                       <img src={`data:image/jpeg;base64,${data.capturedImage}`} className="h-full object-contain rounded-lg opacity-50" />
                    )}
                    <div className="absolute inset-0 flex items-center justify-center">
                       <div className="bg-black/50 backdrop-blur-md px-8 py-4 rounded-xl border border-blue-500/30 flex items-center gap-4">
                          <Loader2 className="animate-spin text-blue-500" />
                          <span className="font-mono text-blue-400 tracking-widest">PROCESSING NERUAL NET...</span>
                       </div>
                    </div>
                 </motion.div>
               )}

               {step === 5 && data.result && (
                 <motion.div 
                   key="result"
                   className="w-full max-w-md bg-white/5 border border-white/10 rounded-2xl p-6 backdrop-blur-sm"
                   initial={{ scale: 0.9, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}
                 >
                    <div className="flex items-start justify-between mb-6">
                       <div>
                         <p className="text-xs text-slate-500 font-mono uppercase mb-1">Classification</p>
                         <h2 className="text-3xl font-bold text-white capitalize">{data.classification}</h2>
                         <div className="flex items-center gap-2 mt-2">
                            <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider ${data.wasteType === 'DRY' ? 'bg-amber-500/20 text-amber-500' : 'bg-blue-500/20 text-blue-500'}`}>
                              {data.wasteType} WASTE
                            </span>
                         </div>
                       </div>
                       {data.result.qr_code && (
                         <img src={`data:image/png;base64,${data.result.qr_code}`} className="w-20 h-20 rounded-lg bg-white p-1" />
                       )}
                    </div>

                    <div className="grid grid-cols-2 gap-4">
                       <ResultStat label="Weight" value={`${data.result.weight}g`} />
                       <ResultStat label="Reward" value={`₹${data.result.amount}`} highlight />
                    </div>
                 </motion.div>
               )}
             </AnimatePresence>
           </div>
        </div>
      </main>
    </div>
  );
};

const PhaseItem = ({ active, label, sub, icon: Icon, step }) => (
  <div className={`p-4 rounded-xl border transition-all duration-500 ${active ? 'bg-white/5 border-white/10 opacity-100' : 'bg-transparent border-transparent opacity-30'}`}>
    <div className="flex items-center gap-4">
      <div className={`p-2 rounded-lg ${active ? 'bg-blue-600' : 'bg-slate-800'}`}>
        <Icon size={16} className="text-white" />
      </div>
      <div>
        <h4 className="font-bold text-sm text-slate-200">{label}</h4>
        <p className="text-[10px] text-slate-500 font-mono tracking-wider uppercase">PHASE 0{step}</p>
      </div>
    </div>
  </div>
);

const Stat = ({ label, value }) => (
  <div className="flex flex-col">
    <span className="text-[10px] text-slate-600 font-bold tracking-widest mb-1">{label}</span>
    <span className="font-mono text-sm text-slate-300">{value}</span>
  </div>
);

const ResultStat = ({ label, value, highlight }) => (
  <div className="bg-[#050505] p-3 rounded-lg border border-white/5">
     <p className="text-[10px] text-slate-500 uppercase tracking-wider font-bold mb-1">{label}</p>
     <p className={`text-xl font-mono ${highlight ? 'text-emerald-500' : 'text-slate-300'}`}>{value}</p>
  </div>
);

export default App;