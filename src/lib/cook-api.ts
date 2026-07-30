import { apiUrl } from "./api-config";
import { clearSession, sessionAuthHeaders } from "./session";
import { AuthError } from "./board-api";

async function getJson<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...init,
    headers: { ...sessionAuthHeaders(), ...(init?.headers ?? {}) },
  });
  if (res.status === 401) {
    clearSession();
    throw new AuthError("session expired or signed out");
  }
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(text || `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export type ProduceLot = {
  id: string;
  name: string;
  quantity: number;
  unit: string;
  status: string;
  storage_location: string;
  traceability: string;
  allergens: string[];
};

export type Ingredient = {
  id: string;
  name: string;
  category: string;
  allergens: string[];
};

export type Dish = {
  id: string;
  name: string;
  type: string;
  status: string;
};

export type CookConsultation = {
  id: string;
  mode: string;
  title: string;
  ingredients_or_problem: string;
  produce_lot_ids: string[];
  ingredient_ids: string[];
  dish_id: string | null;
  traceability: string;
  service_context: string;
  allergens: string[];
  covers_or_portions: number | null;
  time_available_minutes: number | null;
  equipment: string[];
  desired_outcome: string;
  local_safety_plan: {
    decision: { verdict: string; title: string; summary: string };
    recommended_action: string;
    primary_plan: Record<string, unknown>;
    alternatives: { title: string; summary: string; steps?: string[] }[];
    recipe_spine: {
      purpose: string;
      mise: string;
      method: string;
      holding_regeneration: string;
      pass_finish: string;
      failure_recovery: string;
    };
    allergen_checks: string[];
    service_checks: string[];
    disposal_checklist: string[];
    kitchen_memory: { title: string; path: string; relevance: string; excerpt: string }[];
    guest_service_allowed: boolean;
    rejected: boolean;
    notes: string[];
  };
  graph_recall_status: string;
  graph_recall_response: Record<string, unknown> | null;
  task_status: string;
  audit: { at: string; event: string; [k: string]: unknown }[];
  created_at: string;
  updated_at: string;
  blocked_reason: string | null;
};

export async function listProduce() {
  return getJson<ProduceLot[]>(apiUrl("/v1/kitchen/produce"));
}
export async function createProduce(body: Record<string, unknown>) {
  return getJson<ProduceLot>(apiUrl("/v1/kitchen/produce"), {
    method: "POST",
    body: JSON.stringify(body),
  });
}
export async function listIngredients() {
  return getJson<Ingredient[]>(apiUrl("/v1/kitchen/ingredients"));
}
export async function createIngredient(body: Record<string, unknown>) {
  return getJson<Ingredient>(apiUrl("/v1/kitchen/ingredients"), {
    method: "POST",
    body: JSON.stringify(body),
  });
}
export async function listDishes() {
  return getJson<Dish[]>(apiUrl("/v1/kitchen/dishes"));
}
export async function createConsultation(body: Record<string, unknown>) {
  return getJson<CookConsultation>(apiUrl("/v1/cook/consultations"), {
    method: "POST",
    body: JSON.stringify(body),
  });
}
export async function listConsultations(active = false) {
  return getJson<CookConsultation[]>(
    apiUrl(`/v1/cook/consultations${active ? "?active=true" : ""}`),
  );
}
export async function getConsultation(id: string) {
  return getJson<CookConsultation>(apiUrl(`/v1/cook/consultations/${id}`));
}
export async function saveDishFromConsultation(id: string, name?: string) {
  return getJson<Dish>(apiUrl(`/v1/cook/consultations/${id}/save-dish`), {
    method: "POST",
    body: JSON.stringify({ name: name || null, type: "dish", status: "draft" }),
  });
}
export async function completeConsultation(id: string) {
  return getJson<CookConsultation>(apiUrl(`/v1/cook/consultations/${id}/complete`), {
    method: "POST",
    body: "{}",
  });
}
