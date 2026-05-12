"use client";

import { useEffect, useState, useRef } from "react";
import { contactsApi } from "@/lib/api";

// ── Config de colunas ──────────────────────────────────────────────────────────
const ESTAGIOS = [
  { id: "lead",            label: "Lead",         color: "bg-gray-100  border-gray-200",  dot: "bg-gray-400"   },
  { id: "primeiro_contato",label: "1º Contato",   color: "bg-blue-50   border-blue-200",  dot: "bg-blue-400"   },
  { id: "ativo",           label: "Ativo",        color: "bg-green-50  border-green-200", dot: "bg-green-500"  },
  { id: "fidelizado",      label: "Fidelizado",   color: "bg-yellow-50 border-yellow-200",dot: "bg-yellow-500" },
  { id: "inativo",         label: "Inativo",      color: "bg-red-50    border-red-200",   dot: "bg-red-400"    },
];

const TIER_COLORS = {
  vip:      "border-l-yellow-400",
  regular:  "border-l-blue-400",
  new:      "border-l-green-400",
  inactive: "border-l-gray-300",
};

// ── Card de contato ─────────────────────────────────────────────────────────────
function ContactCard({ contact, onDragStart }) {
  return (
    <div
      draggable
      onDragStart={() => onDragStart(contact)}
      className={`bg-white rounded-lg border-l-4 ${TIER_COLORS[contact.tier] ?? "border-l-gray-200"} border border-gray-100 p-3 shadow-sm cursor-grab active:cursor-grabbing hover:shadow-md transition select-none`}
    >
      <p className="font-semibold text-sm text-gray-900 truncate">{contact.nome}</p>
      <p className="text-xs text-gray-500 mt-0.5">{contact.telefone}</p>

      <div className="flex items-center justify-between mt-2">
        <span className={`text-xs px-1.5 py-0.5 rounded font-medium
          ${contact.tier === "vip"     ? "bg-yellow-100 text-yellow-800" : ""}
          ${contact.tier === "regular" ? "bg-blue-100   text-blue-800"   : ""}
          ${contact.tier === "new"     ? "bg-green-100  text-green-800"  : ""}
          ${contact.tier === "inactive"? "bg-gray-100   text-gray-500"   : ""}
        `}>
          {contact.tier?.toUpperCase()}
        </span>
        {contact.total_reservas > 0 && (
          <span className="text-xs text-gray-400">{contact.total_reservas} reservas</span>
        )}
      </div>

      {contact.preferencias && (
        <p className="text-xs text-gray-400 mt-1.5 truncate">⭐ {contact.preferencias}</p>
      )}
    </div>
  );
}

// ── Coluna Kanban ───────────────────────────────────────────────────────────────
function KanbanColumn({ estagio, contacts, onDrop, onDragOver, onDragLeave, isOver }) {
  return (
    <div
      className={`flex flex-col min-h-[600px] w-64 flex-shrink-0 rounded-xl border-2 transition
        ${estagio.color}
        ${isOver ? "border-indigo-400 ring-2 ring-indigo-200" : "border-transparent"}
      `}
      onDragOver={(e) => { e.preventDefault(); onDragOver(estagio.id); }}
      onDragLeave={onDragLeave}
      onDrop={() => onDrop(estagio.id)}
    >
      {/* Column header */}
      <div className="flex items-center gap-2 px-4 py-3 border-b border-black/5">
        <span className={`w-2 h-2 rounded-full ${estagio.dot}`} />
        <span className="font-semibold text-sm text-gray-800">{estagio.label}</span>
        <span className="ml-auto bg-white text-gray-600 text-xs px-2 py-0.5 rounded-full border">
          {contacts.length}
        </span>
      </div>

      {/* Cards */}
      <div className="flex flex-col gap-2 p-3 flex-1 overflow-y-auto">
        {contacts.length === 0 && (
          <div className="flex-1 flex items-center justify-center">
            <p className="text-xs text-gray-400 text-center">Arraste contatos aqui</p>
          </div>
        )}
        {contacts.map((c) => (
          <ContactCard key={c.id} contact={c} onDragStart={() => {}} />
        ))}
      </div>
    </div>
  );
}

// ── Página Kanban ───────────────────────────────────────────────────────────────
export default function KanbanPage() {
  const [columns, setColumns]   = useState({});     // { estagio_id: [contacts] }
  const [loading, setLoading]   = useState(true);
  const [overCol, setOverCol]   = useState(null);
  const dragging                = useRef(null);

  const loadAll = async () => {
    setLoading(true);
    try {
      // Busca todos (sem paginação) para o kanban — máximo 200
      const results = await Promise.all(
        ESTAGIOS.map((e) =>
          contactsApi.list({ pageSize: 100, estgio: e.id }).then((r) => ({
            id: e.id,
            contacts: r.contacts,
          }))
        )
      );
      const map = {};
      results.forEach(({ id, contacts }) => { map[id] = contacts; });
      setColumns(map);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadAll(); }, []);

  const handleDragStart = (contact) => {
    dragging.current = contact;
  };

  const handleDrop = async (targetEstagio) => {
    const contact = dragging.current;
    if (!contact || contact.estagio_kanban === targetEstagio) {
      setOverCol(null);
      return;
    }

    // Optimistic update
    setColumns((prev) => {
      const next = { ...prev };
      next[contact.estagio_kanban] = (next[contact.estagio_kanban] ?? []).filter((c) => c.id !== contact.id);
      next[targetEstagio] = [{ ...contact, estagio_kanban: targetEstagio }, ...(next[targetEstagio] ?? [])];
      return next;
    });

    setOverCol(null);
    dragging.current = null;

    try {
      await contactsApi.moveKanban(contact.id, targetEstagio);
    } catch {
      // Rollback on error
      loadAll();
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64 text-gray-400">
        Carregando kanban...
      </div>
    );
  }

  return (
    <div className="p-6 overflow-x-auto min-h-screen">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Kanban de Contatos</h1>
        <p className="text-sm text-gray-500 mt-1">
          Arraste os cards entre colunas para mudar o estágio do relacionamento
        </p>
      </div>

      <div className="flex gap-4 pb-6" style={{ minWidth: `${ESTAGIOS.length * 272}px` }}>
        {ESTAGIOS.map((e) => (
          <KanbanColumn
            key={e.id}
            estagio={e}
            contacts={columns[e.id] ?? []}
            isOver={overCol === e.id}
            onDragOver={(id) => setOverCol(id)}
            onDragLeave={() => setOverCol(null)}
            onDrop={handleDrop}
          />
        ))}
      </div>
    </div>
  );
}
