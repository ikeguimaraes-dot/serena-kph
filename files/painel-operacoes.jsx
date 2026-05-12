import { useState, useEffect } from "react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, LineChart, Line, CartesianGrid } from "recharts";

// ── Mock data ─────────────────────────────────────────────────
const UNITS = [
  { id: "unidade_jardins", nome: "Jardins" },
  { id: "unidade_itaim",   nome: "Itaim Bibi" },
  { id: "unidade_pinheiros", nome: "Pinheiros" },
  { id: "unidade_moema",   nome: "Moema" },
];

const TODAY_RESERVATIONS = [
  { id:"R7K2A1", nome:"Lucas Ferreira",   hora:"12:00", pessoas:2, status:"confirmada", telefone:"+5511999990001" },
  { id:"M3X9B2", nome:"Mariana Costa",    hora:"13:00", pessoas:4, status:"confirmada", telefone:"+5511999990002" },
  { id:"P1Y4C3", nome:"Ricardo Alves",    hora:"13:30", pessoas:6, status:"confirmada", telefone:"+5511999990003" },
  { id:"Q8Z5D4", nome:"Fernanda Lima",    hora:"19:00", pessoas:2, status:"confirmada", telefone:"+5511999990004" },
  { id:"W2V6E5", nome:"Carlos Mendes",    hora:"20:00", pessoas:8, status:"confirmada", telefone:"+5511999990005" },
  { id:"T9U7F6", nome:"Juliana Rocha",    hora:"20:30", pessoas:3, status:"cancelada",  telefone:"+5511999990006" },
  { id:"S4T8G7", nome:"André Souza",      hora:"21:00", pessoas:5, status:"confirmada", telefone:"+5511999990007" },
  { id:"N6R1H8", nome:"Beatriz Nunes",    hora:"21:30", pessoas:2, status:"no_show",    telefone:"+5511999990008" },
];

const HANDOFFS = [
  { id:1, user_phone:"+5511999990021", motivo:"Cliente solicitou informação sobre menu de degustação especial", status:"aguardando",      created_at:"há 3 min"  },
  { id:2, user_phone:"+5511999990022", motivo:"Reclamação sobre reserva cancelada indevidamente",               status:"em_atendimento", created_at:"há 12 min", atendente:"Sofia" },
  { id:3, user_phone:"+5511999990023", motivo:"Solicita reserva para grupo de 15 pessoas",                      status:"aguardando",      created_at:"há 28 min" },
];

const CONVERSATIONS = [
  { user_phone:"+5511999990031", ultima:"Quero reservar para amanhã às 20h", created_at:"há 2 min",  tipo:"reserva" },
  { user_phone:"+5511999990032", ultima:"Vocês têm opção vegana?",             created_at:"há 8 min",  tipo:"duvida" },
  { user_phone:"+5511999990033", ultima:"Qual o preço do menu degustação?",    created_at:"há 15 min", tipo:"duvida" },
  { user_phone:"+5511999990034", ultima:"Preciso cancelar minha reserva",      created_at:"há 22 min", tipo:"cancelamento" },
  { user_phone:"+5511999990035", ultima:"Obrigado, até sábado!",               created_at:"há 45 min", tipo:"concluido" },
];

const MENU_ITEMS = [
  { id:1, categoria:"Entradas",        nome:"Burrata com tomate confit",    preco:68,  disponivel:true  },
  { id:2, categoria:"Entradas",        nome:"Carpaccio de wagyu",           preco:95,  disponivel:true  },
  { id:3, categoria:"Entradas",        nome:"Vieiras grelhadas",            preco:82,  disponivel:false },
  { id:4, categoria:"Pratos Principais",nome:"Picanha dry-aged 300g",      preco:165, disponivel:true  },
  { id:5, categoria:"Pratos Principais",nome:"Linguado ao limão-siciliano", preco:148, disponivel:true  },
  { id:6, categoria:"Pratos Principais",nome:"Risoto de funghi com trufa",  preco:138, disponivel:true  },
  { id:7, categoria:"Sobremesas",       nome:"Soufflé de chocolate",        preco:52,  disponivel:true  },
  { id:8, categoria:"Sobremesas",       nome:"Petit gâteau com sorvete",    preco:48,  disponivel:true  },
];

const CHART_DATA = [
  { dia:"Seg", reservas:12 }, { dia:"Ter", reservas:18 }, { dia:"Qua", reservas:22 },
  { dia:"Qui", reservas:19 }, { dia:"Sex", reservas:34 }, { dia:"Sáb", reservas:41 },
  { dia:"Dom", reservas:29 },
];

const PEAK_HOURS = [
  { hora:"12:00", pessoas:24 }, { hora:"13:00", pessoas:38 }, { hora:"14:00", pessoas:18 },
  { hora:"19:00", pessoas:22 }, { hora:"20:00", pessoas:52 }, { hora:"21:00", pessoas:48 },
  { hora:"22:00", pessoas:31 },
];

// ── Status pill ───────────────────────────────────────────────
function StatusPill({ status }) {
  const map = {
    confirmada:    ["#16a34a","#dcfce7"],
    cancelada:     ["#dc2626","#fee2e2"],
    no_show:       ["#92400e","#fef3c7"],
    concluida:     ["#475569","#f1f5f9"],
    aguardando:    ["#b45309","#fef3c7"],
    em_atendimento:["#1d4ed8","#dbeafe"],
    resolvido:     ["#16a34a","#dcfce7"],
  };
  const [color, bg] = map[status] || ["#64748b","#f1f5f9"];
  const labels = { confirmada:"Confirmada", cancelada:"Cancelada", no_show:"No-show",
    concluida:"Concluída", aguardando:"Aguardando", em_atendimento:"Em atendimento", resolvido:"Resolvido" };
  return (
    <span style={{ background:bg, color, fontSize:11, fontWeight:700,
      padding:"2px 10px", borderRadius:99, letterSpacing:.5, textTransform:"uppercase" }}>
      {labels[status] || status}
    </span>
  );
}

// ── Stat card ─────────────────────────────────────────────────
function StatCard({ label, value, sub, accent }) {
  return (
    <div style={{ background:"#fff", border:"1px solid #e8e3da", borderRadius:16,
      padding:"24px 28px", display:"flex", flexDirection:"column", gap:8 }}>
      <span style={{ fontSize:12, fontWeight:600, color:"#94a3b8", letterSpacing:1, textTransform:"uppercase" }}>{label}</span>
      <span style={{ fontSize:36, fontWeight:800, color: accent || "#1a1a18", lineHeight:1 }}>{value}</span>
      {sub && <span style={{ fontSize:13, color:"#64748b" }}>{sub}</span>}
    </div>
  );
}

// ── Section header ────────────────────────────────────────────
function SectionHeader({ title, action }) {
  return (
    <div style={{ display:"flex", alignItems:"center", justifyContent:"space-between", marginBottom:20 }}>
      <h2 style={{ fontSize:18, fontWeight:800, color:"#1a1a18", margin:0, fontFamily:"'Playfair Display',Georgia,serif" }}>{title}</h2>
      {action}
    </div>
  );
}

// ── Button ────────────────────────────────────────────────────
function Btn({ children, onClick, variant="primary", small }) {
  const styles = {
    primary: { background:"#1a1a18", color:"#fff", border:"none" },
    ghost:   { background:"transparent", color:"#1a1a18", border:"1.5px solid #e8e3da" },
    danger:  { background:"#fee2e2", color:"#dc2626", border:"none" },
    success: { background:"#dcfce7", color:"#16a34a", border:"none" },
  };
  return (
    <button onClick={onClick} style={{
      ...styles[variant], borderRadius:10, padding: small ? "6px 14px" : "10px 20px",
      fontSize: small ? 12 : 14, fontWeight:700, cursor:"pointer",
      fontFamily:"'DM Sans',sans-serif", letterSpacing:.3
    }}>{children}</button>
  );
}

// ── VIEWS ─────────────────────────────────────────────────────

function DashboardView({ unit }) {
  return (
    <div style={{ display:"flex", flexDirection:"column", gap:28 }}>
      {/* Stats */}
      <div style={{ display:"grid", gridTemplateColumns:"repeat(4,1fr)", gap:16 }}>
        <StatCard label="Reservas Hoje"     value="32"    sub="↑ 6 vs ontem"         />
        <StatCard label="Pessoas Esperadas" value="128"   sub="capacidade: 80/turno"  />
        <StatCard label="Reservas no Mês"   value="347"   sub="↑ 18% vs mês anterior" accent="#2563eb" />
        <StatCard label="Handoffs Abertos"  value="3"     sub="2 aguardando resposta" accent="#dc2626" />
      </div>

      {/* Reservas de hoje */}
      <div style={{ background:"#fff", border:"1px solid #e8e3da", borderRadius:16, padding:28 }}>
        <SectionHeader title={`Reservas de Hoje — ${unit}`} />
        <table style={{ width:"100%", borderCollapse:"collapse" }}>
          <thead>
            <tr style={{ borderBottom:"2px solid #f1f5f9" }}>
              {["Código","Nome","Horário","Pessoas","Status","Ação"].map(h => (
                <th key={h} style={{ textAlign:"left", padding:"8px 12px", fontSize:11,
                  fontWeight:700, color:"#94a3b8", letterSpacing:1, textTransform:"uppercase" }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {TODAY_RESERVATIONS.map(r => (
              <tr key={r.id} style={{ borderBottom:"1px solid #f8f9fa" }}>
                <td style={{ padding:"14px 12px", fontFamily:"monospace", fontWeight:700, color:"#64748b", fontSize:13 }}>{r.id}</td>
                <td style={{ padding:"14px 12px", fontWeight:600, color:"#1a1a18" }}>{r.nome}</td>
                <td style={{ padding:"14px 12px", color:"#475569", fontWeight:600 }}>{r.hora}</td>
                <td style={{ padding:"14px 12px", color:"#475569" }}>{r.pessoas} pax</td>
                <td style={{ padding:"14px 12px" }}><StatusPill status={r.status} /></td>
                <td style={{ padding:"14px 12px", display:"flex", gap:8 }}>
                  <Btn small variant="ghost">Ver</Btn>
                  {r.status === "confirmada" && <Btn small variant="danger">Cancelar</Btn>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Handoff queue */}
      {HANDOFFS.filter(h => h.status !== "resolvido").length > 0 && (
        <div style={{ background:"#fff8f1", border:"1.5px solid #fed7aa", borderRadius:16, padding:28 }}>
          <SectionHeader title="⚡ Handoffs Pendentes" />
          <div style={{ display:"flex", flexDirection:"column", gap:12 }}>
            {HANDOFFS.filter(h => h.status !== "resolvido").map(h => (
              <div key={h.id} style={{ background:"#fff", border:"1px solid #e8e3da", borderRadius:12,
                padding:"16px 20px", display:"flex", alignItems:"center", gap:16 }}>
                <div style={{ flex:1 }}>
                  <div style={{ fontSize:13, fontWeight:700, color:"#1a1a18" }}>{h.user_phone}</div>
                  <div style={{ fontSize:13, color:"#64748b", marginTop:4 }}>{h.motivo}</div>
                  <div style={{ fontSize:11, color:"#94a3b8", marginTop:4 }}>{h.created_at}</div>
                </div>
                <StatusPill status={h.status} />
                <Btn small>Assumir</Btn>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function ReservasView() {
  const [filter, setFilter] = useState("todas");
  const filtered = filter === "todas" ? TODAY_RESERVATIONS : TODAY_RESERVATIONS.filter(r => r.status === filter);
  return (
    <div style={{ background:"#fff", border:"1px solid #e8e3da", borderRadius:16, padding:28 }}>
      <SectionHeader title="Gestão de Reservas" action={
        <div style={{ display:"flex", gap:8 }}>
          {["todas","confirmada","cancelada","no_show"].map(f => (
            <button key={f} onClick={() => setFilter(f)} style={{
              padding:"6px 16px", borderRadius:99, border:"1.5px solid",
              borderColor: filter===f ? "#1a1a18" : "#e8e3da",
              background: filter===f ? "#1a1a18" : "transparent",
              color: filter===f ? "#fff" : "#64748b",
              fontSize:12, fontWeight:700, cursor:"pointer", textTransform:"capitalize"
            }}>{f === "no_show" ? "No-show" : f.charAt(0).toUpperCase()+f.slice(1)}</button>
          ))}
        </div>
      } />
      <table style={{ width:"100%", borderCollapse:"collapse" }}>
        <thead>
          <tr style={{ borderBottom:"2px solid #f1f5f9" }}>
            {["Código","Nome","Telefone","Data","Horário","Pax","Status",""].map(h => (
              <th key={h} style={{ textAlign:"left", padding:"8px 12px", fontSize:11,
                fontWeight:700, color:"#94a3b8", letterSpacing:1 }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {filtered.map(r => (
            <tr key={r.id} style={{ borderBottom:"1px solid #f8f9fa" }}>
              <td style={{ padding:"14px 12px", fontFamily:"monospace", fontWeight:700, color:"#64748b", fontSize:13 }}>{r.id}</td>
              <td style={{ padding:"14px 12px", fontWeight:600 }}>{r.nome}</td>
              <td style={{ padding:"14px 12px", color:"#64748b", fontSize:13 }}>{r.telefone}</td>
              <td style={{ padding:"14px 12px", color:"#64748b" }}>19/04/2026</td>
              <td style={{ padding:"14px 12px", fontWeight:600 }}>{r.hora}</td>
              <td style={{ padding:"14px 12px" }}>{r.pessoas}</td>
              <td style={{ padding:"14px 12px" }}><StatusPill status={r.status} /></td>
              <td style={{ padding:"14px 12px" }}>
                <div style={{ display:"flex", gap:6 }}>
                  <Btn small variant="ghost">Editar</Btn>
                  {r.status==="confirmada" && <Btn small variant="danger">×</Btn>}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ConversasView() {
  const [selected, setSelected] = useState(null);
  const [reply, setReply] = useState("");

  const mockHistory = [
    { role:"user", content:"Boa tarde! Gostaria de fazer uma reserva para sábado." },
    { role:"assistant", content:"Boa tarde! Fico feliz em ajudar. Para quantas pessoas e qual horário você prefere?" },
    { role:"user", content:"São 4 pessoas, às 20h." },
    { role:"assistant", content:"Perfeito. Deixa eu verificar a disponibilidade... Temos sim! Para confirmar, qual é o nome para a reserva?" },
    { role:"user", content:"Lucas Ferreira" },
    { role:"assistant", content:"Reserva confirmada ✅\nCódigo: *R7K2A1*\nNome: Lucas Ferreira\nData: 22/04/2026 às 20h\nPessoas: 4\n\nGuarde o código para consultas ou cancelamentos." },
  ];

  return (
    <div style={{ display:"grid", gridTemplateColumns:"320px 1fr", gap:20, height:600 }}>
      {/* Lista */}
      <div style={{ background:"#fff", border:"1px solid #e8e3da", borderRadius:16, overflow:"hidden" }}>
        <div style={{ padding:"20px 20px 16px", borderBottom:"1px solid #f1f5f9",
          fontSize:14, fontWeight:800, color:"#1a1a18", fontFamily:"'Playfair Display',Georgia,serif" }}>
          Conversas Ativas
        </div>
        <div style={{ overflowY:"auto", height:"calc(100% - 57px)" }}>
          {[...HANDOFFS.map(h => ({ user_phone:h.user_phone, ultima:h.motivo, created_at:h.created_at, tipo:"handoff" })),
            ...CONVERSATIONS].map((c, i) => (
            <div key={i} onClick={() => setSelected(c)} style={{
              padding:"16px 20px", borderBottom:"1px solid #f8f9fa", cursor:"pointer",
              background: selected?.user_phone===c.user_phone ? "#f8f6f1" : "transparent",
              borderLeft: c.tipo==="handoff" ? "3px solid #f97316" : "3px solid transparent",
              transition:"background .15s"
            }}>
              <div style={{ display:"flex", justifyContent:"space-between", marginBottom:4 }}>
                <span style={{ fontSize:13, fontWeight:700, color:"#1a1a18" }}>{c.user_phone}</span>
                <span style={{ fontSize:11, color:"#94a3b8" }}>{c.created_at}</span>
              </div>
              <div style={{ fontSize:12, color:"#64748b", whiteSpace:"nowrap", overflow:"hidden", textOverflow:"ellipsis" }}>{c.ultima}</div>
              {c.tipo==="handoff" && <div style={{ fontSize:11, color:"#f97316", fontWeight:700, marginTop:4 }}>⚡ Aguarda atendimento</div>}
            </div>
          ))}
        </div>
      </div>

      {/* Chat */}
      <div style={{ background:"#fff", border:"1px solid #e8e3da", borderRadius:16,
        display:"flex", flexDirection:"column", overflow:"hidden" }}>
        {selected ? (
          <>
            <div style={{ padding:"20px 24px", borderBottom:"1px solid #f1f5f9",
              display:"flex", alignItems:"center", justifyContent:"space-between" }}>
              <div>
                <div style={{ fontSize:15, fontWeight:800, color:"#1a1a18" }}>{selected.user_phone}</div>
                <div style={{ fontSize:12, color:"#94a3b8" }}>Histórico de conversa</div>
              </div>
              <div style={{ display:"flex", gap:8 }}>
                <Btn small variant="success">Resolver</Btn>
                <Btn small variant="ghost">Ver reservas</Btn>
              </div>
            </div>
            <div style={{ flex:1, overflowY:"auto", padding:"20px 24px", display:"flex", flexDirection:"column", gap:12 }}>
              {mockHistory.map((m, i) => (
                <div key={i} style={{
                  alignSelf: m.role==="user" ? "flex-start" : "flex-end",
                  maxWidth:"72%",
                  background: m.role==="user" ? "#f1f5f9" : "#1a1a18",
                  color: m.role==="user" ? "#1a1a18" : "#fff",
                  borderRadius: m.role==="user" ? "4px 16px 16px 16px" : "16px 4px 16px 16px",
                  padding:"12px 16px", fontSize:14, lineHeight:1.5, whiteSpace:"pre-wrap"
                }}>{m.content}</div>
              ))}
            </div>
            <div style={{ padding:"16px 24px", borderTop:"1px solid #f1f5f9", display:"flex", gap:12 }}>
              <input
                value={reply}
                onChange={e => setReply(e.target.value)}
                placeholder="Responder como atendente..."
                style={{ flex:1, padding:"12px 16px", border:"1.5px solid #e8e3da",
                  borderRadius:12, fontSize:14, fontFamily:"'DM Sans',sans-serif", outline:"none" }}
              />
              <Btn onClick={() => setReply("")}>Enviar</Btn>
            </div>
          </>
        ) : (
          <div style={{ flex:1, display:"flex", alignItems:"center", justifyContent:"center", color:"#94a3b8", fontSize:15 }}>
            Selecione uma conversa
          </div>
        )}
      </div>
    </div>
  );
}

function CardapioView() {
  const [items, setItems] = useState(MENU_ITEMS);
  const [adding, setAdding] = useState(false);
  const [newItem, setNewItem] = useState({ categoria:"", nome:"", preco:"", descricao:"" });
  const categorias = [...new Set(items.map(i => i.categoria))];

  const toggleDisp = (id) => setItems(prev => prev.map(i => i.id===id ? {...i, disponivel:!i.disponivel} : i));

  return (
    <div style={{ display:"flex", flexDirection:"column", gap:24 }}>
      <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center" }}>
        <h2 style={{ fontSize:18, fontWeight:800, color:"#1a1a18", margin:0, fontFamily:"'Playfair Display',Georgia,serif" }}>Gestão de Cardápio</h2>
        <Btn onClick={() => setAdding(!adding)}>{adding ? "Cancelar" : "+ Novo Item"}</Btn>
      </div>

      {adding && (
        <div style={{ background:"#f8f6f1", border:"1.5px solid #e8e3da", borderRadius:16, padding:24 }}>
          <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr 1fr 1fr", gap:16, marginBottom:16 }}>
            {[["Categoria","categoria","Entradas"],["Nome","nome","Ex: Burrata"],["Preço","preco","R$ 00"],["Descrição","descricao","Opcional"]].map(([label,key,ph]) => (
              <div key={key}>
                <label style={{ fontSize:12, fontWeight:700, color:"#64748b", display:"block", marginBottom:6 }}>{label}</label>
                <input
                  value={newItem[key]}
                  onChange={e => setNewItem(p => ({...p,[key]:e.target.value}))}
                  placeholder={ph}
                  style={{ width:"100%", padding:"10px 14px", border:"1.5px solid #e8e3da",
                    borderRadius:10, fontSize:14, fontFamily:"'DM Sans',sans-serif",
                    boxSizing:"border-box", outline:"none" }}
                />
              </div>
            ))}
          </div>
          <Btn onClick={() => {
            if (newItem.nome && newItem.categoria) {
              setItems(p => [...p, { id: Date.now(), ...newItem, preco: parseFloat(newItem.preco)||0, disponivel:true }]);
              setNewItem({ categoria:"", nome:"", preco:"", descricao:"" });
              setAdding(false);
            }
          }}>Salvar Item</Btn>
        </div>
      )}

      {categorias.map(cat => (
        <div key={cat} style={{ background:"#fff", border:"1px solid #e8e3da", borderRadius:16, overflow:"hidden" }}>
          <div style={{ padding:"16px 24px", background:"#f8f6f1", borderBottom:"1px solid #e8e3da",
            fontSize:13, fontWeight:800, color:"#1a1a18", letterSpacing:.5, textTransform:"uppercase" }}>{cat}</div>
          <table style={{ width:"100%", borderCollapse:"collapse" }}>
            <tbody>
              {items.filter(i => i.categoria===cat).map(item => (
                <tr key={item.id} style={{ borderBottom:"1px solid #f8f9fa", opacity: item.disponivel ? 1 : .5 }}>
                  <td style={{ padding:"16px 24px" }}>
                    <div style={{ fontWeight:700, color:"#1a1a18" }}>{item.nome}</div>
                    {item.descricao && <div style={{ fontSize:12, color:"#94a3b8", marginTop:2 }}>{item.descricao}</div>}
                  </td>
                  <td style={{ padding:"16px 24px", fontWeight:700, color:"#1a1a18" }}>R$ {item.preco}</td>
                  <td style={{ padding:"16px 24px" }}>
                    <button onClick={() => toggleDisp(item.id)} style={{
                      padding:"4px 14px", borderRadius:99, border:"1.5px solid",
                      borderColor: item.disponivel ? "#16a34a" : "#e8e3da",
                      background: item.disponivel ? "#dcfce7" : "#f8f9fa",
                      color: item.disponivel ? "#16a34a" : "#94a3b8",
                      fontSize:12, fontWeight:700, cursor:"pointer"
                    }}>{item.disponivel ? "Disponível" : "Indisponível"}</button>
                  </td>
                  <td style={{ padding:"16px 24px" }}>
                    <div style={{ display:"flex", gap:8 }}>
                      <Btn small variant="ghost">Editar</Btn>
                      <Btn small variant="danger">Remover</Btn>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </div>
  );
}

function RelatoriosView() {
  return (
    <div style={{ display:"flex", flexDirection:"column", gap:24 }}>
      <div style={{ display:"grid", gridTemplateColumns:"repeat(3,1fr)", gap:16 }}>
        <StatCard label="Taxa de Conversão"   value="38%"  sub="conversas → reservas" accent="#2563eb" />
        <StatCard label="Taxa de Cancelamento" value="6.2%" sub="no mês atual"         accent="#f97316" />
        <StatCard label="NPS (estimado)"       value="72"   sub="baseado em recorrência" accent="#16a34a" />
      </div>

      <div style={{ background:"#fff", border:"1px solid #e8e3da", borderRadius:16, padding:28 }}>
        <h3 style={{ fontSize:16, fontWeight:800, color:"#1a1a18", marginBottom:24, fontFamily:"'Playfair Display',Georgia,serif" }}>Reservas por Dia (últimos 7 dias)</h3>
        <ResponsiveContainer width="100%" height={240}>
          <BarChart data={CHART_DATA} barSize={40}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
            <XAxis dataKey="dia" tick={{ fontSize:12, fill:"#94a3b8" }} axisLine={false} tickLine={false} />
            <YAxis tick={{ fontSize:12, fill:"#94a3b8" }} axisLine={false} tickLine={false} />
            <Tooltip contentStyle={{ border:"1px solid #e8e3da", borderRadius:10, fontSize:13 }} />
            <Bar dataKey="reservas" fill="#1a1a18" radius={[6,6,0,0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div style={{ background:"#fff", border:"1px solid #e8e3da", borderRadius:16, padding:28 }}>
        <h3 style={{ fontSize:16, fontWeight:800, color:"#1a1a18", marginBottom:24, fontFamily:"'Playfair Display',Georgia,serif" }}>Horários de Pico (cobertura em pax)</h3>
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={PEAK_HOURS}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
            <XAxis dataKey="hora" tick={{ fontSize:12, fill:"#94a3b8" }} axisLine={false} tickLine={false} />
            <YAxis tick={{ fontSize:12, fill:"#94a3b8" }} axisLine={false} tickLine={false} />
            <Tooltip contentStyle={{ border:"1px solid #e8e3da", borderRadius:10, fontSize:13 }} />
            <Line type="monotone" dataKey="pessoas" stroke="#2563eb" strokeWidth={2.5} dot={{ fill:"#2563eb", r:4 }} />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:20 }}>
        <div style={{ background:"#fff", border:"1px solid #e8e3da", borderRadius:16, padding:28 }}>
          <h3 style={{ fontSize:15, fontWeight:800, color:"#1a1a18", marginBottom:20, fontFamily:"'Playfair Display',Georgia,serif" }}>Top Horários</h3>
          {PEAK_HOURS.sort((a,b)=>b.pessoas-a.pessoas).slice(0,5).map((h,i) => (
            <div key={h.hora} style={{ display:"flex", alignItems:"center", gap:12, marginBottom:14 }}>
              <span style={{ fontSize:12, fontWeight:800, color:"#94a3b8", width:20 }}>#{i+1}</span>
              <span style={{ fontWeight:700, color:"#1a1a18", width:60 }}>{h.hora}</span>
              <div style={{ flex:1, height:6, background:"#f1f5f9", borderRadius:99, overflow:"hidden" }}>
                <div style={{ height:"100%", background:"#1a1a18", borderRadius:99, width:`${h.pessoas/52*100}%` }} />
              </div>
              <span style={{ fontSize:13, color:"#64748b", width:40, textAlign:"right" }}>{h.pessoas} pax</span>
            </div>
          ))}
        </div>
        <div style={{ background:"#fff", border:"1px solid #e8e3da", borderRadius:16, padding:28 }}>
          <h3 style={{ fontSize:15, fontWeight:800, color:"#1a1a18", marginBottom:20, fontFamily:"'Playfair Display',Georgia,serif" }}>Performance Mensal</h3>
          {[
            { label:"Total de conversas",       value:"912" },
            { label:"Reservas realizadas",       value:"347" },
            { label:"Cancelamentos",             value:"22"  },
            { label:"Handoffs para equipe",      value:"38"  },
            { label:"Taxa de resolução da IA",   value:"96%" },
          ].map(({ label, value }) => (
            <div key={label} style={{ display:"flex", justifyContent:"space-between",
              padding:"10px 0", borderBottom:"1px solid #f8f9fa" }}>
              <span style={{ fontSize:14, color:"#64748b" }}>{label}</span>
              <span style={{ fontSize:14, fontWeight:800, color:"#1a1a18" }}>{value}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ── APP PRINCIPAL ─────────────────────────────────────────────

const VIEWS = [
  { id:"dashboard",  label:"Dashboard",   icon:"⬛" },
  { id:"reservas",   label:"Reservas",    icon:"📅" },
  { id:"conversas",  label:"Conversas",   icon:"💬" },
  { id:"cardapio",   label:"Cardápio",    icon:"🍽️" },
  { id:"relatorios", label:"Relatórios",  icon:"📊" },
];

export default function App() {
  const [view, setView]       = useState("dashboard");
  const [unit, setUnit]       = useState(UNITS[0]);
  const [time, setTime]       = useState(new Date().toLocaleTimeString("pt-BR",{hour:"2-digit",minute:"2-digit"}));

  useEffect(() => {
    const t = setInterval(() => setTime(new Date().toLocaleTimeString("pt-BR",{hour:"2-digit",minute:"2-digit"})), 30000);
    return () => clearInterval(t);
  }, []);

  const badge = HANDOFFS.filter(h => h.status !== "resolvido").length;

  return (
    <div style={{ display:"flex", height:"100vh", fontFamily:"'DM Sans',sans-serif",
      background:"#f8f6f1", color:"#1a1a18" }}>

      {/* Sidebar */}
      <div style={{ width:240, background:"#1a1a18", display:"flex", flexDirection:"column",
        padding:"32px 0", flexShrink:0 }}>
        <div style={{ padding:"0 28px 32px", borderBottom:"1px solid #2d2d2a" }}>
          <div style={{ fontSize:18, fontWeight:900, color:"#fff", letterSpacing:-.5,
            fontFamily:"'Playfair Display',Georgia,serif" }}>Restaurant AI</div>
          <div style={{ fontSize:11, color:"#6b6b65", marginTop:4, letterSpacing:.5 }}>PAINEL DE OPERAÇÕES</div>
        </div>

        {/* Seletor de unidade */}
        <div style={{ padding:"20px 20px 8px" }}>
          <div style={{ fontSize:10, color:"#6b6b65", fontWeight:700, letterSpacing:1, marginBottom:8 }}>UNIDADE</div>
          <select
            value={unit.id}
            onChange={e => setUnit(UNITS.find(u => u.id===e.target.value))}
            style={{ width:"100%", background:"#2d2d2a", color:"#fff", border:"none",
              borderRadius:10, padding:"10px 14px", fontSize:13, fontWeight:600,
              fontFamily:"'DM Sans',sans-serif", cursor:"pointer" }}
          >
            {UNITS.map(u => <option key={u.id} value={u.id}>{u.nome}</option>)}
          </select>
        </div>

        <nav style={{ flex:1, padding:"12px 12px" }}>
          {VIEWS.map(v => (
            <button key={v.id} onClick={() => setView(v.id)} style={{
              width:"100%", display:"flex", alignItems:"center", gap:12,
              padding:"12px 16px", borderRadius:12, border:"none", cursor:"pointer",
              background: view===v.id ? "#2d2d2a" : "transparent",
              color: view===v.id ? "#fff" : "#6b6b65",
              fontSize:14, fontWeight: view===v.id ? 700 : 500,
              textAlign:"left", position:"relative", marginBottom:2, transition:"all .15s"
            }}>
              <span style={{ fontSize:16 }}>{v.icon}</span>
              {v.label}
              {v.id==="conversas" && badge > 0 && (
                <span style={{ position:"absolute", right:12, background:"#f97316",
                  color:"#fff", fontSize:10, fontWeight:900, borderRadius:99,
                  padding:"2px 7px", minWidth:18, textAlign:"center" }}>{badge}</span>
              )}
            </button>
          ))}
        </nav>

        <div style={{ padding:"20px 24px", borderTop:"1px solid #2d2d2a" }}>
          <div style={{ fontSize:11, color:"#6b6b65" }}>Atualizado</div>
          <div style={{ fontSize:14, fontWeight:700, color:"#fff" }}>{time}</div>
        </div>
      </div>

      {/* Main */}
      <div style={{ flex:1, display:"flex", flexDirection:"column", overflow:"hidden" }}>
        {/* Topbar */}
        <div style={{ padding:"20px 40px", background:"#fff", borderBottom:"1px solid #e8e3da",
          display:"flex", alignItems:"center", justifyContent:"space-between" }}>
          <div>
            <h1 style={{ fontSize:22, fontWeight:900, color:"#1a1a18", margin:0,
              fontFamily:"'Playfair Display',Georgia,serif" }}>
              {VIEWS.find(v => v.id===view)?.label}
            </h1>
            <div style={{ fontSize:12, color:"#94a3b8", marginTop:2 }}>
              {unit.nome} · Domingo, 19 de Abril de 2026
            </div>
          </div>
          <div style={{ display:"flex", gap:12, alignItems:"center" }}>
            {badge > 0 && (
              <div style={{ background:"#fff3e0", color:"#f97316", padding:"8px 16px",
                borderRadius:99, fontSize:13, fontWeight:700, cursor:"pointer" }}
                onClick={() => setView("conversas")}>
                ⚡ {badge} handoff{badge>1?"s":""} pendente{badge>1?"s":""}
              </div>
            )}
            <div style={{ width:36, height:36, background:"#1a1a18", borderRadius:99,
              display:"flex", alignItems:"center", justifyContent:"center",
              fontSize:16, cursor:"pointer" }}>👤</div>
          </div>
        </div>

        {/* Content */}
        <div style={{ flex:1, overflowY:"auto", padding:"32px 40px" }}>
          {view === "dashboard"  && <DashboardView  unit={unit.nome} />}
          {view === "reservas"   && <ReservasView   />}
          {view === "conversas"  && <ConversasView  />}
          {view === "cardapio"   && <CardapioView   />}
          {view === "relatorios" && <RelatoriosView />}
        </div>
      </div>

      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700;800;900&family=DM+Sans:wght@400;500;600;700;800&display=swap');
        * { box-sizing: border-box; }
        button:hover { opacity: .88; }
        ::-webkit-scrollbar { width: 6px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: #e8e3da; border-radius: 99px; }
      `}</style>
    </div>
  );
}
