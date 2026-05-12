"use client";

import { useEffect, useState, useCallback } from "react";
import { contactsApi } from "@/lib/api";

// ── Tier badge ─────────────────────────────────────────────────────────────────
const TIER_COLORS = {
  vip:      "bg-yellow-100 text-yellow-800",
  regular:  "bg-blue-100 text-blue-800",
  new:      "bg-green-100 text-green-800",
  inactive: "bg-gray-100 text-gray-500",
};

const ESTAGIO_LABELS = {
  lead:            "Lead",
  primeiro_contato:"1º Contato",
  ativo:           "Ativo",
  fidelizado:      "Fidelizado",
  inativo:         "Inativo",
};

function TierBadge({ tier }) {
  return (
    <span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${TIER_COLORS[tier] ?? "bg-gray-100"}`}>
      {tier?.toUpperCase()}
    </span>
  );
}

// ── Drawer lateral ─────────────────────────────────────────────────────────────
function ContactDrawer({ contact, onClose, onSave }) {
  const [form, setForm] = useState({});
  const [loading, setLoading] = useState(false);
  const [tab, setTab] = useState("info"); // info | reservas | conversas
  const [reservas, setReservas] = useState([]);
  const [conversas, setConversas] = useState([]);

  useEffect(() => {
    if (!contact) return;
    setForm({
      nome:                   contact.nome ?? "",
      telefone:               contact.telefone ?? "",
      email:                  contact.email ?? "",
      preferencias:           contact.preferencias ?? "",
      restricoes_alimentares: contact.restricoes_alimentares ?? "",
      notas_internas:         contact.notas_internas ?? "",
      estagio_kanban:         contact.estagio_kanban ?? "lead",
    });
  }, [contact]);

  const loadTab = useCallback(async (t) => {
    setTab(t);
    if (t === "reservas" && reservas.length === 0) {
      const r = await contactsApi.reservations(contact.id);
      setReservas(r.reservations ?? []);
    }
    if (t === "conversas" && conversas.length === 0) {
      const r = await contactsApi.conversations(contact.id);
      setConversas(r.conversations ?? []);
    }
  }, [contact, reservas, conversas]);

  const handleSave = async () => {
    setLoading(true);
    try {
      await contactsApi.update(contact.id, form);
      onSave();
    } finally {
      setLoading(false);
    }
  };

  if (!contact) return null;

  return (
    <div className="fixed inset-0 z-50 flex">
      {/* Overlay */}
      <div className="flex-1 bg-black/40" onClick={onClose} />

      {/* Drawer */}
      <div className="w-[480px] bg-white h-full shadow-2xl flex flex-col overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b">
          <div>
            <p className="font-semibold text-lg">{contact.nome}</p>
            <p className="text-sm text-gray-500">{contact.telefone}</p>
          </div>
          <div className="flex items-center gap-3">
            <TierBadge tier={contact.tier} />
            <button onClick={onClose} className="text-gray-400 hover:text-gray-700 text-xl">✕</button>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex border-b text-sm font-medium">
          {["info", "reservas", "conversas"].map((t) => (
            <button
              key={t}
              onClick={() => loadTab(t)}
              className={`px-5 py-2.5 capitalize transition ${tab === t ? "border-b-2 border-indigo-600 text-indigo-600" : "text-gray-500 hover:text-gray-800"}`}
            >
              {t}
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6">
          {tab === "info" && (
            <div className="space-y-4">
              {[
                ["Nome",  "nome",  "text"],
                ["Telefone", "telefone", "text"],
                ["Email", "email", "email"],
              ].map(([label, key, type]) => (
                <div key={key}>
                  <label className="block text-xs font-medium text-gray-500 mb-1">{label}</label>
                  <input
                    type={type}
                    value={form[key] ?? ""}
                    onChange={(e) => setForm(f => ({ ...f, [key]: e.target.value }))}
                    className="w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
                  />
                </div>
              ))}

              <div>
                <label className="block text-xs font-medium text-gray-500 mb-1">Estágio Kanban</label>
                <select
                  value={form.estagio_kanban ?? "lead"}
                  onChange={(e) => setForm(f => ({ ...f, estagio_kanban: e.target.value }))}
                  className="w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
                >
                  {Object.entries(ESTAGIO_LABELS).map(([v, l]) => (
                    <option key={v} value={v}>{l}</option>
                  ))}
                </select>
              </div>

              {[
                ["Preferências", "preferencias"],
                ["Restrições Alimentares", "restricoes_alimentares"],
                ["Notas Internas", "notas_internas"],
              ].map(([label, key]) => (
                <div key={key}>
                  <label className="block text-xs font-medium text-gray-500 mb-1">{label}</label>
                  <textarea
                    rows={3}
                    value={form[key] ?? ""}
                    onChange={(e) => setForm(f => ({ ...f, [key]: e.target.value }))}
                    className="w-full border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300 resize-none"
                  />
                </div>
              ))}
            </div>
          )}

          {tab === "reservas" && (
            <div className="space-y-3">
              {reservas.length === 0
                ? <p className="text-sm text-gray-400">Nenhuma reserva encontrada</p>
                : reservas.map((r) => (
                  <div key={r.id} className="border rounded-lg p-3 text-sm">
                    <p className="font-medium">{r.data} — {r.horario}</p>
                    <p className="text-gray-500">{r.pessoas} pessoas · {r.status}</p>
                    {r.notas && <p className="text-gray-400 text-xs mt-1">{r.notas}</p>}
                  </div>
                ))
              }
            </div>
          )}

          {tab === "conversas" && (
            <div className="space-y-3">
              {conversas.length === 0
                ? <p className="text-sm text-gray-400">Nenhuma conversa encontrada</p>
                : conversas.map((c, i) => (
                  <div key={i} className="border rounded-lg p-3 text-sm">
                    <p className="text-gray-500 text-xs">{c.created_at}</p>
                    <p className="mt-1">{c.resumo ?? c.mensagem ?? "—"}</p>
                  </div>
                ))
              }
            </div>
          )}
        </div>

        {/* Footer */}
        {tab === "info" && (
          <div className="px-6 py-4 border-t flex justify-end gap-3">
            <button onClick={onClose} className="px-4 py-2 text-sm rounded-lg border hover:bg-gray-50">
              Cancelar
            </button>
            <button
              onClick={handleSave}
              disabled={loading}
              className="px-5 py-2 text-sm rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50"
            >
              {loading ? "Salvando..." : "Salvar"}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Página principal ───────────────────────────────────────────────────────────
export default function ContatosPage() {
  const [contacts, setContacts]   = useState([]);
  const [total, setTotal]         = useState(0);
  const [page, setPage]           = useState(1);
  const [search, setSearch]       = useState("");
  const [filterTier, setFilterTier] = useState("");
  const [selected, setSelected]   = useState(null);
  const [loading, setLoading]     = useState(false);
  const [stats, setStats]         = useState(null);

  const PAGE_SIZE = 25;

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await contactsApi.list({
        page, pageSize: PAGE_SIZE,
        tier: filterTier || undefined,
        search: search || undefined,
      });
      setContacts(data.contacts);
      setTotal(data.total);
    } finally {
      setLoading(false);
    }
  }, [page, search, filterTier]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    contactsApi.stats().then(setStats).catch(() => {});
  }, []);

  const handleSave = () => {
    setSelected(null);
    load();
  };

  const totalPages = Math.ceil(total / PAGE_SIZE);

  return (
    <div className="p-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Contatos</h1>
          {stats && (
            <p className="text-sm text-gray-500 mt-0.5">
              {stats.total} contatos · {stats.vip} VIP · {stats.regular} regulares
            </p>
          )}
        </div>
      </div>

      {/* Filters */}
      <div className="flex gap-3 mb-5">
        <input
          type="text"
          placeholder="Buscar nome ou telefone..."
          value={search}
          onChange={(e) => { setSearch(e.target.value); setPage(1); }}
          className="flex-1 border rounded-lg px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
        />
        <select
          value={filterTier}
          onChange={(e) => { setFilterTier(e.target.value); setPage(1); }}
          className="border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
        >
          <option value="">Todos os tiers</option>
          <option value="vip">VIP</option>
          <option value="regular">Regular</option>
          <option value="new">Novo</option>
          <option value="inactive">Inativo</option>
        </select>
      </div>

      {/* Table */}
      <div className="bg-white rounded-xl border shadow-sm overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-gray-500 text-xs uppercase tracking-wide">
            <tr>
              {["Nome", "Telefone", "Email", "Tier", "Estágio", "Visitas", "Última visita"].map((h) => (
                <th key={h} className="px-4 py-3 text-left font-medium">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {loading
              ? <tr><td colSpan={7} className="px-4 py-8 text-center text-gray-400">Carregando...</td></tr>
              : contacts.length === 0
                ? <tr><td colSpan={7} className="px-4 py-8 text-center text-gray-400">Nenhum contato encontrado</td></tr>
                : contacts.map((c) => (
                  <tr
                    key={c.id}
                    onClick={() => setSelected(c)}
                    className="hover:bg-indigo-50 cursor-pointer transition"
                  >
                    <td className="px-4 py-3 font-medium text-gray-900">{c.nome}</td>
                    <td className="px-4 py-3 text-gray-600">{c.telefone}</td>
                    <td className="px-4 py-3 text-gray-500">{c.email ?? "—"}</td>
                    <td className="px-4 py-3"><TierBadge tier={c.tier} /></td>
                    <td className="px-4 py-3 text-gray-600">{ESTAGIO_LABELS[c.estagio_kanban] ?? c.estagio_kanban}</td>
                    <td className="px-4 py-3 text-center text-gray-700">{c.total_reservas}</td>
                    <td className="px-4 py-3 text-gray-500">
                      {c.ultima_visita ? new Date(c.ultima_visita).toLocaleDateString("pt-BR") : "—"}
                    </td>
                  </tr>
                ))
            }
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between mt-4 text-sm text-gray-600">
          <span>{total} contatos no total</span>
          <div className="flex gap-2">
            <button
              disabled={page === 1}
              onClick={() => setPage(p => p - 1)}
              className="px-3 py-1.5 border rounded hover:bg-gray-50 disabled:opacity-40"
            >
              ← Anterior
            </button>
            <span className="px-3 py-1.5">Página {page} de {totalPages}</span>
            <button
              disabled={page === totalPages}
              onClick={() => setPage(p => p + 1)}
              className="px-3 py-1.5 border rounded hover:bg-gray-50 disabled:opacity-40"
            >
              Próxima →
            </button>
          </div>
        </div>
      )}

      {/* Drawer */}
      <ContactDrawer contact={selected} onClose={() => setSelected(null)} onSave={handleSave} />
    </div>
  );
}
