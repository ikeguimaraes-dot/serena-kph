// ─── painel/src/lib/api.js — adicionar aos métodos existentes ────────────────

// ── Contacts ──────────────────────────────────────────────────────────────────

export const contactsApi = {

  /** Lista contatos com filtros opcionais */
  list: async ({ page = 1, pageSize = 20, tier, estgio, search } = {}) => {
    const params = new URLSearchParams({ page, page_size: pageSize });
    if (tier)    params.set("tier", tier);
    if (estgio)  params.set("estagio_kanban", estgio);
    if (search)  params.set("search", search);

    const res = await fetch(`${API_BASE}/contacts?${params}`);
    if (!res.ok) throw new Error("Erro ao buscar contatos");
    return res.json(); // { contacts, total, page, page_size }
  },

  /** Busca um contato por ID */
  get: async (id) => {
    const res = await fetch(`${API_BASE}/contacts/${id}`);
    if (!res.ok) throw new Error("Contato não encontrado");
    return res.json();
  },

  /** Cria contato manual */
  create: async (data) => {
    const res = await fetch(`${API_BASE}/contacts`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    if (!res.ok) throw new Error("Erro ao criar contato");
    return res.json();
  },

  /** Atualiza campos parciais */
  update: async (id, updates) => {
    const res = await fetch(`${API_BASE}/contacts/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(updates),
    });
    if (!res.ok) throw new Error("Erro ao atualizar contato");
    return res.json();
  },

  /** Move no kanban */
  moveKanban: async (id, estagio_kanban) => {
    const res = await fetch(`${API_BASE}/contacts/${id}/kanban`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ estagio_kanban }),
    });
    if (!res.ok) throw new Error("Erro ao mover contato");
    return res.json();
  },

  /** Histórico de reservas do contato */
  reservations: async (id) => {
    const res = await fetch(`${API_BASE}/contacts/${id}/reservations`);
    if (!res.ok) throw new Error("Erro ao buscar reservas");
    return res.json();
  },

  /** Histórico de conversas do contato */
  conversations: async (id) => {
    const res = await fetch(`${API_BASE}/contacts/${id}/conversations`);
    if (!res.ok) throw new Error("Erro ao buscar conversas");
    return res.json();
  },

  /** Stats gerais (dashboard) */
  stats: async () => {
    const res = await fetch(`${API_BASE}/contacts/stats`);
    if (!res.ok) throw new Error("Erro ao buscar stats");
    return res.json();
  },
};
