'use client';
import { useState, useCallback, useEffect, useRef } from 'react';
import { LiveKitRoom, useVoiceAssistant, RoomAudioRenderer } from '@livekit/components-react';
import '@livekit/components-styles';

export default function Home() {
  const [token, setToken] = useState('');
  const [url, setUrl] = useState('');
  const [connected, setConnected] = useState(false);
  const [loading, setLoading] = useState(false);

  const connect = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/token');
      const data = await res.json();
      setToken(data.token);
      setUrl(data.url);
      setConnected(true);
    } catch (e) {
      alert('Failed to connect. Is your Python agent running?');
    } finally {
      setLoading(false);
    }
  }, []);

  const disconnect = useCallback(() => {
    setConnected(false);
    setToken('');
  }, []);

  if (!connected) {
    return (
      <div style={{minHeight:'100vh',background:'#0a0a0a',display:'flex',alignItems:'center',justifyContent:'center',fontFamily:'"JetBrains Mono",monospace',position:'relative',overflow:'hidden'}}>
        <div style={{position:'absolute',inset:0,backgroundImage:'linear-gradient(rgba(255,34,34,0.03) 1px,transparent 1px),linear-gradient(90deg,rgba(255,34,34,0.03) 1px,transparent 1px)',backgroundSize:'40px 40px',pointerEvents:'none'}}/>
        <div style={{textAlign:'center',display:'flex',flexDirection:'column',alignItems:'center',gap:'40px',zIndex:1,padding:'24px'}}>
          <div style={{display:'flex',alignItems:'center',gap:'12px',padding:'6px 16px',border:'1px solid #2a1a1a',background:'#150d0d'}}>
            <div style={{width:'6px',height:'6px',borderRadius:'50%',background:'#ff2222',boxShadow:'0 0 8px #ff2222'}}/>
            <span style={{color:'#ff2222',fontSize:'11px',letterSpacing:'0.2em'}}>SYSTEM READY</span>
          </div>
          <div>
            <div style={{color:'#3a1a1a',fontSize:'11px',letterSpacing:'0.3em',marginBottom:'12px'}}>// VOICE INTERFACE v1.0</div>
            <h1 style={{fontSize:'clamp(2rem,5vw,4rem)',fontWeight:'700',color:'#ffffff',margin:'0 0 8px',letterSpacing:'-0.02em',lineHeight:1}}>
              VOICE<span style={{color:'#ff2222'}}>_</span>AI
            </h1>
            <p style={{color:'#4a6a4a',fontSize:'12px',margin:0,letterSpacing:'0.15em'}}>ULTRA-LOW LATENCY · PERSISTENT MEMORY</p>
          </div>
          <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:'1px',background:'#2a1a1a',border:'1px solid #2a1a1a',width:'100%',maxWidth:'420px'}}>
            {[
              ['STT','DEEPGRAM NOVA-2'],
              ['LLM','GEMINI 2.5 FLASH'],
              ['TTS','DEEPGRAM AURA-2'],
              ['CONTROL','COMPUTER USE MCP'],
              ['VISION','SCREEN PERCEPTION'],
              ['NET','LIVEKIT CLOUD'],
            ].map(([k,v])=>(
              <div key={k} style={{background:'#0a0a0a',padding:'10px 14px'}}>
                <div style={{color:'#4a2a2a',fontSize:'9px',letterSpacing:'0.2em',marginBottom:'3px'}}>{k}</div>
                <div style={{color:'#ff2222',fontSize:'10px',letterSpacing:'0.05em'}}>{v}</div>
              </div>
            ))}
          </div>
          <div style={{display:'flex',gap:'8px',flexWrap:'wrap',justifyContent:'center',maxWidth:'460px',fontSize:'9px',color:'#5a3a3a',letterSpacing:'0.12em'}}>
            <span style={{border:'1px solid #2a1a1a',padding:'4px 8px',background:'#0f0a0a'}}>📸 SCREENSHOTS & VISION</span>
            <span style={{border:'1px solid #2a1a1a',padding:'4px 8px',background:'#0f0a0a'}}>🖱️ MOUSE AUTOMATION</span>
            <span style={{border:'1px solid #2a1a1a',padding:'4px 8px',background:'#0f0a0a'}}>⌨️ KEYBOARD & SHORTCUTS</span>
            <span style={{border:'1px solid #2a1a1a',padding:'4px 8px',background:'#0f0a0a'}}>🚀 APP LAUNCHER</span>
          </div>
          <button onClick={connect} disabled={loading} style={{padding:'14px 48px',background:'transparent',border:'1px solid #ff2222',color:'#ff2222',fontSize:'12px',fontWeight:'700',letterSpacing:'0.2em',cursor:loading?'not-allowed':'pointer',fontFamily:'"JetBrains Mono",monospace',transition:'all 0.2s',boxShadow:loading?'none':'0 0 20px rgba(255,34,34,0.15)'}}>
            {loading ? 'INITIALIZING...' : '[ CONNECT ]'}
          </button>
        </div>
      </div>
    );
  }

  return (
    <LiveKitRoom
      token={token}
      serverUrl={url}
      connect={true}
      audio={{
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      }}
      video={false}
      onDisconnected={disconnect}
      style={{width:'100%',height:'100vh',background:'#0a0a0a'}}
    >
      <VoiceUI onDisconnect={disconnect} />
      <RoomAudioRenderer />
    </LiveKitRoom>
  );
}

type Mode = 'natural' | 'warm' | 'professional' | 'spicy';

const MODE_COLORS: Record<Mode, string> = {
  natural:      '#00cc66',
  warm:         '#ff8844',
  professional: '#4488ff',
  spicy:        '#ff2222',
};

const MODE_LABELS: Record<Mode, string> = {
  natural:      'NATURAL',
  warm:         'WARM',
  professional: 'PROFESSIONAL',
  spicy:        'SPICY',
};

function detectMode(text: string): Mode | null {
  const t = text.toLowerCase();
  if (t.includes('natural') || t.includes('casual mode')) return 'natural';
  if (t.includes('warm') || t.includes('sweet mode')) return 'warm';
  if (t.includes('professional') || t.includes('work mode')) return 'professional';
  if (t.includes('spicy') || t.includes('flirt') || t.includes('sexy mode')) return 'spicy';
  return null;
}

function VoiceUI({ onDisconnect }: { onDisconnect: () => void }) {
  const { state, agentTranscriptions, userTranscriptions } = useVoiceAssistant() as any;
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animRef = useRef<number>(0);
  const [duration, setDuration] = useState(0);
  const [messages, setMessages] = useState<{role:string,text:string,time:string}[]>([]);
  const [mode, setMode] = useState<Mode>('natural');
  const startTime = useRef(Date.now());
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const lastAgentIdx = useRef(-1);
  const lastUserIdx = useRef(-1);

  useEffect(()=>{
    const t = setInterval(()=>setDuration(Math.floor((Date.now()-startTime.current)/1000)),1000);
    return ()=>clearInterval(t);
  },[]);

  useEffect(()=>{
    messagesEndRef.current?.scrollIntoView({behavior:'smooth'});
  },[messages]);

  useEffect(()=>{
    if (!agentTranscriptions?.length) return;
    const newOnes = agentTranscriptions.slice(lastAgentIdx.current + 1);
    if (!newOnes.length) return;
    lastAgentIdx.current = agentTranscriptions.length - 1;
    const toAdd = newOnes
      .filter((t: any) => t?.text?.trim())
      .map((t: any) => ({ role: 'agent', text: t.text, time: new Date().toLocaleTimeString() }));
    if (toAdd.length) setMessages(prev => [...prev, ...toAdd]);
  }, [agentTranscriptions]);

  useEffect(()=>{
    if (!userTranscriptions?.length) return;
    const newOnes = userTranscriptions.slice(lastUserIdx.current + 1);
    if (!newOnes.length) return;
    lastUserIdx.current = userTranscriptions.length - 1;
    const toAdd = newOnes
      .filter((t: any) => t?.text?.trim())
      .map((t: any) => ({ role: 'user', text: t.text, time: new Date().toLocaleTimeString() }));
    if (toAdd.length) {
      setMessages(prev => [...prev, ...toAdd]);
      toAdd.forEach((m: any) => {
        const detected = detectMode(m.text);
        if (detected) setMode(detected);
      });
    }
  }, [userTranscriptions]);

  const modeColor = MODE_COLORS[mode];
  const stateColor = state==='listening'?'#ff2222':state==='thinking'?'#ffaa00':state==='speaking'?'#00aaff':'#2a3a2a';
  const stateLabel = state==='listening'?'LISTENING':state==='thinking'?'PROCESSING':state==='speaking'?'TRANSMITTING':'STANDBY';

  useEffect(()=>{
    const canvas = canvasRef.current;
    if(!canvas) return;
    const ctx = canvas.getContext('2d')!;
    let t = 0;
    const draw = ()=>{
      const W=canvas.width=400, H=canvas.height=400;
      ctx.clearRect(0,0,W,H);
      const cx=W/2, cy=H/2;
      const active = state==='speaking'||state==='listening';

      if(active){
        ctx.save();
        ctx.translate(cx,cy);
        const sweep = (t*0.02)%(Math.PI*2);
        for(let i=0;i<60;i++){
          const a = sweep-(i/60)*Math.PI*0.5;
          const alpha = (1-i/60)*0.15;
          ctx.beginPath();
          ctx.moveTo(0,0);
          ctx.arc(0,0,160,a,a+0.05);
          ctx.fillStyle = stateColor+Math.floor(alpha*255).toString(16).padStart(2,'0');
          ctx.fill();
        }
        ctx.restore();
      }

      [160,120,80,40].forEach((r,i)=>{
        ctx.beginPath();
        ctx.arc(cx,cy,r,0,Math.PI*2);
        ctx.strokeStyle = i===0?stateColor+'33':stateColor+'11';
        ctx.lineWidth=1;
        ctx.stroke();
      });

      ctx.strokeStyle = stateColor+'22';
      ctx.lineWidth=1;
      ctx.beginPath(); ctx.moveTo(cx,cy-170); ctx.lineTo(cx,cy+170); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(cx-170,cy); ctx.lineTo(cx+170,cy); ctx.stroke();

      const pulse = active ? 4+Math.sin(t*0.1)*3 : 4;
      ctx.beginPath();
      ctx.arc(cx,cy,pulse,0,Math.PI*2);
      ctx.fillStyle = stateColor;
      ctx.shadowColor = stateColor;
      ctx.shadowBlur = active?20:0;
      ctx.fill();
      ctx.shadowBlur=0;

      if(active){
        const bars=32;
        for(let i=0;i<bars;i++){
          const a=(i/bars)*Math.PI*2;
          const h=8+Math.abs(Math.sin(t*0.06+i*0.4))*30;
          const r1=50, r2=r1+h;
          ctx.beginPath();
          ctx.moveTo(cx+Math.cos(a)*r1,cy+Math.sin(a)*r1);
          ctx.lineTo(cx+Math.cos(a)*r2,cy+Math.sin(a)*r2);
          ctx.strokeStyle=stateColor+'99';
          ctx.lineWidth=2;
          ctx.stroke();
        }
      }

      [[cx-160,cy-160],[cx+160,cy-160],[cx-160,cy+160],[cx+160,cy+160]].forEach(([x,y])=>{
        ctx.strokeStyle=stateColor+'44';
        ctx.lineWidth=1;
        const s=10;
        ctx.beginPath();
        ctx.moveTo(x,y+s); ctx.lineTo(x,y); ctx.lineTo(x+(x<cx?1:-1)*s,y);
        ctx.stroke();
      });

      t++; animRef.current=requestAnimationFrame(draw);
    };
    draw();
    return ()=>cancelAnimationFrame(animRef.current);
  },[state,stateColor]);

  const fmt = (s:number)=>`${String(Math.floor(s/60)).padStart(2,'0')}:${String(s%60).padStart(2,'0')}`;

  return (
    <div style={{width:'100%',height:'100vh',background:'#0a0a0a',display:'flex',flexDirection:'column',fontFamily:'"JetBrains Mono",monospace',overflow:'hidden'}}>
      <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',padding:'12px 24px',borderBottom:'1px solid #2a1a1a',background:'#0d0d0d'}}>
        <div style={{display:'flex',alignItems:'center',gap:'16px'}}>
          <span style={{color:'#ff2222',fontSize:'12px',letterSpacing:'0.15em',fontWeight:'700'}}>VOICE_AI</span>
          <span style={{color:'#2a3a2a',fontSize:'10px'}}>|</span>
          <span style={{color:'#4a2a2a',fontSize:'10px',letterSpacing:'0.1em'}}>SESSION ACTIVE</span>
        </div>
        <div style={{display:'flex',alignItems:'center',gap:'16px'}}>
          <div style={{display:'flex',alignItems:'center',gap:'6px',padding:'3px 10px',border:`1px solid ${modeColor}44`,background:`${modeColor}11`}}>
            <div style={{width:'5px',height:'5px',borderRadius:'50%',background:modeColor,boxShadow:`0 0 6px ${modeColor}`}}/>
            <span style={{color:modeColor,fontSize:'9px',letterSpacing:'0.15em'}}>{MODE_LABELS[mode]}</span>
          </div>
          <span style={{color:'#4a2a2a',fontSize:'10px',letterSpacing:'0.1em'}}>DURATION: <span style={{color:'#ff2222'}}>{fmt(duration)}</span></span>
          <div style={{width:'6px',height:'6px',borderRadius:'50%',background:stateColor,boxShadow:`0 0 8px ${stateColor}`}}/>
        </div>
      </div>

      <div style={{flex:1,display:'flex',overflow:'hidden'}}>
        <div style={{flex:1,display:'flex',flexDirection:'column',alignItems:'center',justifyContent:'center',position:'relative',borderRight:'1px solid #2a1a1a'}}>
          <div style={{position:'absolute',top:'20px',left:'50%',transform:'translateX(-50%)',display:'flex',alignItems:'center',gap:'8px'}}>
            <div style={{width:'5px',height:'5px',borderRadius:'50%',background:stateColor,boxShadow:`0 0 6px ${stateColor}`}}/>
            <span style={{color:stateColor,fontSize:'10px',letterSpacing:'0.2em'}}>{stateLabel}</span>
          </div>

          <canvas ref={canvasRef} style={{width:'400px',height:'400px',maxWidth:'90vw',maxHeight:'50vh'}}/>

          <div style={{position:'absolute',bottom:'20px',left:'50%',transform:'translateX(-50%)',textAlign:'center'}}>
            <div style={{color:'#3a1a1a',fontSize:'10px',letterSpacing:'0.15em'}}>
              {state==='listening'?'// SPEAK NOW':state==='thinking'?'// PROCESSING INPUT':state==='speaking'?'// RECEIVING OUTPUT':'// AWAITING INPUT'}
            </div>
          </div>
        </div>

        <div style={{width:'280px',display:'flex',flexDirection:'column',background:'#0d0d0d'}}>
          <div style={{padding:'16px',borderBottom:'1px solid #2a1a1a'}}>
            <div style={{color:'#4a2a2a',fontSize:'9px',letterSpacing:'0.2em',marginBottom:'12px'}}>// SYSTEM INFO</div>
            {[
              ['LLM','GEMINI 2.5 FLASH'],
              ['STT','DEEPGRAM NOVA-2'],
              ['TTS','DEEPGRAM AURA-2'],
              ['DESKTOP','COMPUTER USE MCP'],
              ['VISION','MULTIMODAL'],
              ['MEMORY','PERSISTENT'],
              ['MODE', MODE_LABELS[mode]],
            ].map(([k,v])=>(
              <div key={k} style={{display:'flex',justifyContent:'space-between',marginBottom:'8px'}}>
                <span style={{color:'#4a2a2a',fontSize:'10px',letterSpacing:'0.1em'}}>{k}</span>
                <span style={{color: k==='MODE' ? modeColor : '#7a4a4a',fontSize:'10px'}}>{v}</span>
              </div>
            ))}
          </div>

          <div style={{flex:1,padding:'16px',overflowY:'auto'}}>
            <div style={{color:'#4a2a2a',fontSize:'9px',letterSpacing:'0.2em',marginBottom:'12px'}}>// TRANSCRIPT</div>
            {messages.length===0 && (
              <div style={{color:'#3a1a1a',fontSize:'10px',lineHeight:1.6}}>awaiting first transmission...</div>
            )}
            {messages.map((m,i)=>(
              <div key={i} style={{marginBottom:'12px'}}>
                <div style={{color:m.role==='user'?'#4a2a2a':'#2a3a4a',fontSize:'9px',letterSpacing:'0.1em',marginBottom:'4px'}}>{m.role==='user'?'USR':'AGT'} · {m.time}</div>
                <div style={{color:m.role==='user'?'#9a6a6a':'#6a8a9a',fontSize:'11px',lineHeight:1.6}}>{m.text}</div>
              </div>
            ))}
            <div ref={messagesEndRef}/>
          </div>

          <div style={{padding:'16px',borderTop:'1px solid #2a1a1a'}}>
            <button onClick={onDisconnect} style={{width:'100%',padding:'10px',background:'transparent',border:'1px solid #2a1a1a',color:'#4a2a2a',fontSize:'10px',letterSpacing:'0.15em',cursor:'pointer',fontFamily:'"JetBrains Mono",monospace',transition:'all 0.2s'}}
              onMouseEnter={e=>{(e.currentTarget as HTMLButtonElement).style.borderColor='#ff3333';(e.currentTarget as HTMLButtonElement).style.color='#ff3333';}}
              onMouseLeave={e=>{(e.currentTarget as HTMLButtonElement).style.borderColor='#2a1a1a';(e.currentTarget as HTMLButtonElement).style.color='#4a2a2a';}}>
              [ DISCONNECT ]
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}