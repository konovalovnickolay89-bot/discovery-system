import { r as __toESM } from "../_runtime.mjs";
import { M as require_react, h as require_jsx_runtime } from "../_libs/@tanstack/react-router+[...].mjs";
//#region node_modules/.nitro/vite/services/ssr/assets/routes-DESaPsBK.js
var import_react = /* @__PURE__ */ __toESM(require_react());
var import_jsx_runtime = require_jsx_runtime();
/** Client fallback if Python API is unreachable (e.g. static preview). */
var FALLBACK_BOARD = {
	header: {
		host: "debian-minimal",
		updated_at: "2026-07-29T12:00:00.000Z",
		status: {
			label: "ok · quiet",
			warnings: 0
		}
	},
	today: {
		items: [
			{
				id: "t1",
				text: "Open: walk-in temps, blast chill log, handwash stations",
				kind: "routine",
				tags: ["routine"],
				level: "info"
			},
			{
				id: "t2",
				text: "11:30 — confirm allergen matrix print for lunch service",
				kind: "reminder",
				tags: ["reminder"],
				level: "warn"
			},
			{
				id: "t3",
				text: "Capture: try brown-butter sage on gnocchi next soft open",
				kind: "capture",
				tags: ["capture"],
				level: "info"
			},
			{
				id: "t4",
				text: "Recipe pin · lemon & herb roast chicken",
				kind: "recipe",
				tags: ["recipe"],
				level: "info",
				recipe: {
					one: "Lemon & herb roast chicken, one tray",
					why: "Quiet service night — high yield, low fuss, parents-friendly",
					how: "Spatchcock · zest under skin · 210°C / 40 min · rest 12",
					roles: "Lead: roast / second: greens + jus / runner: carve station",
					mise_1: "Birds trussed · zest bowl · thyme oil · salt tray · thermometer",
					cost_portion: "£2.40 food · plate £11 · target 68% GP",
					watch: "Thigh joint probe 74°C · don't over-brown zest · hold carve warm",
					allergens: "None intrinsic · check bread crumb garnish if added",
					parents: "No chilli · soft greens option · carve away from bone if asked",
					service_pass: "Half bird + jus spoon · herb oil finish · lemon cheek on rim"
				}
			}
		],
		empty_footer: "routine.json is empty — add your day's shape"
	},
	media: {
		state: "idle",
		current: {
			id: "m0",
			title: "Late Ferry Home",
			artist: "Quiet Harbour"
		},
		queue: [
			{
				id: "m1",
				title: "Cassette Dust",
				artist: "Tape Room"
			},
			{
				id: "m2",
				title: "Kitchen After Close",
				artist: "Line Down"
			},
			{
				id: "m3",
				title: "Soft Grid Rain",
				artist: "Signal Low"
			},
			{
				id: "m4",
				title: "Sunday Prep",
				artist: "Mise en Place"
			}
		],
		cassette: true,
		volume: 55,
		playlist_label: "CHILLOUT MUSIC 2026",
		speaker: "speaker up"
	},
	learning: {
		pool: [
			{
				id: "l1",
				topic: "allergen-matrix",
				primary: "14 major allergens must be presentable from the pass without guessing — matrix lives on the clip, not in someone's head.",
				detail: "Walk the matrix at open: celery, gluten, crustaceans, eggs, fish, lupin, milk, molluscs, mustard, nuts, peanuts, sesame, soya, sulphites. Mark dish changes in red pen before service.",
				tags: ["allergen-matrix", "pass"]
			},
			{
				id: "l2",
				topic: "service-rescue",
				primary: "When a table goes quiet-angry: acknowledge, own one concrete fix, give a time, then deliver — don't over-apologise.",
				detail: "Script: 'You're right — that wait is on us. I'm putting a fresh plate on now; eight minutes, and a drink while you wait.' Then close the loop yourself.",
				tags: ["service-rescue", "front"]
			},
			{
				id: "l3",
				topic: "line-opening",
				primary: "Line open is a checklist, not a vibe: temps, stock, tools, taste, tickets.",
				detail: "Order: (1) temps logged, (2) stock counts, (3) tools staged, (4) taste sauces, (5) ticket rail clear. Only then call line open.",
				tags: ["line-opening", "open"]
			},
			{
				id: "l4",
				topic: "allergen-matrix",
				primary: "Cross-contact is the silent fail: shared fryer oil, same tongs on fish and veg, unlabelled deli tubs.",
				detail: "Separate utensils for allergen-critical plates. Label every mise tub. Second-check the board when a new special lands.",
				tags: ["allergen-matrix", "mise"]
			},
			{
				id: "l5",
				topic: "service-rescue",
				primary: "86'd mid-service: strike the board, tell floor in one sentence, offer the nearest equal dish.",
				detail: "Don't hide 86s. Equal-path: same allergen profile if possible, same price band, same cook time. Write the sub on the docket.",
				tags: ["service-rescue", "board"]
			},
			{
				id: "l6",
				topic: "line-opening",
				primary: "First ticket of the day is a systems test — treat it like a fire drill, not a warm-up plate.",
				detail: "Watch ticket print, station read, cook start, pass call, runner pickup. If the first plate is late, the system is late.",
				tags: ["line-opening", "tickets"]
			}
		],
		window_size: 5,
		ring: 1,
		topics_label: "allergen-matrix + service-rescue + line-opening",
		advance_ms: 2e4
	},
	briefing: {
		pins: [
			{
				id: "p1",
				title: "Morning light on the Pembrokeshire coast path — still empty at 7am",
				url: "https://x.com/explore",
				source: "x",
				level: "info"
			},
			{
				id: "p2",
				title: "Brief note on sleep debt and reaction time — useful for late service weeks",
				url: "https://x.com/explore",
				source: "x",
				level: "info"
			},
			{
				id: "p3",
				title: "A small delight: sourdough that finally holds its ear after 40 tries",
				url: "https://x.com/explore",
				source: "x",
				level: "info"
			}
		],
		ring: [
			{
				id: "r1",
				title: "Show HN: offline-first kitchen ticket rail written in ~400 lines of C",
				url: "https://news.ycombinator.com",
				source: "hn",
				points: 214,
				comments: 89,
				level: "info"
			},
			{
				id: "r2",
				title: "Quiet thread on keeping a home lab boring on purpose",
				url: "https://x.com/explore",
				source: "x",
				level: "info"
			},
			{
				id: "r3",
				title: "Ask HN: how do you structure a personal ops board without it becoming a second job?",
				url: "https://news.ycombinator.com",
				source: "hn",
				points: 156,
				comments: 112,
				level: "info"
			},
			{
				id: "r4",
				title: "Someone posted their cassette deck maintenance checklist — oddly satisfying",
				url: "https://x.com/explore",
				source: "x",
				level: "info"
			},
			{
				id: "r5",
				title: "HN: Practical guide to reading apt and systemd status without the noise",
				url: "https://news.ycombinator.com",
				source: "hn",
				points: 98,
				comments: 41,
				level: "info"
			}
		],
		ring_index: 0,
		ring_n: 1,
		sources_label: "x + hn",
		advance_ms: 5e3
	},
	machine: {
		host: "debian-minimal",
		disk_pct: 42,
		free_gib: 118.4,
		failed_units: 0,
		net: "wired",
		apt_updates: 3,
		warn: false
	}
};
async function getJson(url, init) {
	const res = await fetch(url, {
		...init,
		headers: {
			"content-type": "application/json",
			...init?.headers ?? {}
		}
	});
	if (!res.ok) {
		const text = await res.text().catch(() => "");
		throw new Error(text || `HTTP ${res.status}`);
	}
	return res.json();
}
async function fetchBoard() {
	try {
		return await getJson("/api/board");
	} catch {
		return FALLBACK_BOARD;
	}
}
async function fetchHealth() {
	try {
		return await getJson("/api/health");
	} catch {
		return null;
	}
}
async function postCapture(note) {
	return getJson("/api/ai/capture", {
		method: "POST",
		body: JSON.stringify({ note })
	});
}
async function postLearningExpand(prompt, topic) {
	return getJson("/api/ai/learning", {
		method: "POST",
		body: JSON.stringify({
			prompt,
			topic
		})
	});
}
function formatLocalTime(d) {
	return d.toLocaleTimeString(void 0, {
		hour: "2-digit",
		minute: "2-digit",
		second: "2-digit",
		hour12: false
	});
}
function relativeUpdated(iso, now) {
	const t = new Date(iso).getTime();
	const sec = Math.max(0, Math.floor((now - t) / 1e3));
	if (sec < 5) return "updated just now";
	if (sec < 60) return `updated ${sec}s ago`;
	const min = Math.floor(sec / 60);
	if (min < 60) return `updated ${min}m ago`;
	return `updated ${Math.floor(min / 60)}h ago`;
}
function HeaderBar({ header, health }) {
	const [now, setNow] = (0, import_react.useState)(null);
	(0, import_react.useEffect)(() => {
		setNow(Date.now());
		const id = window.setInterval(() => setNow(Date.now()), 1e3);
		return () => window.clearInterval(id);
	}, []);
	const warn = header.status.warnings > 0;
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("header", {
		className: "header-bar",
		children: [
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
				className: "tabular text-fg",
				children: now == null ? "--:--:--" : formatLocalTime(new Date(now))
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
				className: "sep",
				children: "·"
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { children: header.host }),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
				className: "sep",
				children: "·"
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", { children: now == null ? "updated …" : relativeUpdated(header.updated_at, now) }),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
				className: "sep",
				children: "·"
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
				className: warn ? "status-warn" : "status-ok",
				children: header.status.label
			}),
			health ? /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(import_jsx_runtime.Fragment, { children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
				className: "sep",
				children: "·"
			}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", {
				title: `pydantic ${health.pydantic} · pydantic-ai ${health.pydantic_ai}`,
				children: [
					"py ",
					health.pydantic,
					" · ai ",
					health.pydantic_ai
				]
			})] }) : null
		]
	});
}
function TagChip({ tag }) {
	return /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
		className: "tag-chip",
		children: tag
	});
}
var RECIPE_LABELS = [
	{
		key: "one",
		label: "ONE"
	},
	{
		key: "why",
		label: "WHY"
	},
	{
		key: "how",
		label: "HOW"
	},
	{
		key: "roles",
		label: "ROLES"
	},
	{
		key: "mise_1",
		label: "MISE 1"
	},
	{
		key: "cost_portion",
		label: "COST/PORTION"
	},
	{
		key: "watch",
		label: "WATCH"
	},
	{
		key: "allergens",
		label: "ALLERGENS"
	},
	{
		key: "parents",
		label: "PARENTS"
	},
	{
		key: "service_pass",
		label: "SERVICE/PASS"
	}
];
function ItemBlock({ item }) {
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		className: "item-row",
		children: [
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
				className: `level-${item.level}`,
				children: item.text
			}),
			item.tags?.length ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
				className: "mt-1 flex flex-wrap gap-1",
				children: item.tags.map((t) => /* @__PURE__ */ (0, import_jsx_runtime.jsx)(TagChip, { tag: t }, t))
			}) : null,
			item.url ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("a", {
				className: "item-url",
				href: item.url,
				target: "_blank",
				rel: "noreferrer",
				children: item.url
			}) : null,
			item.recipe ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("dl", {
				className: "recipe-spine",
				children: RECIPE_LABELS.map(({ key, label }) => /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", { children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("dt", { children: label }), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("dd", { children: item.recipe[key] })] }, key))
			}) : null
		]
	});
}
function TodayCard({ board, onBoard }) {
	const { today } = board;
	const [note, setNote] = (0, import_react.useState)("");
	const [busy, setBusy] = (0, import_react.useState)(false);
	const [meta, setMeta] = (0, import_react.useState)(null);
	const [err, setErr] = (0, import_react.useState)(null);
	async function submitCapture() {
		if (!note.trim() || busy) return;
		setBusy(true);
		setErr(null);
		try {
			const res = await postCapture(note.trim());
			setMeta(`${res.meta.engine} · ${res.meta.model} · ${res.meta.validated_by}`);
			const item = {
				id: `cap-local-${Date.now()}`,
				text: `${res.draft.title} — ${res.draft.body}`,
				kind: "capture",
				tags: res.draft.tags,
				level: res.draft.level
			};
			onBoard({
				...board,
				today: {
					...board.today,
					items: [...board.today.items, item]
				}
			});
			setNote("");
		} catch (e) {
			setErr(e instanceof Error ? e.message : "capture failed");
		} finally {
			setBusy(false);
		}
	}
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("section", {
		className: "board-card",
		"data-accent": "peach",
		"aria-label": "today",
		children: [
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("h2", {
				className: "board-card-title",
				"data-accent": "peach",
				children: "today"
			}),
			today.items.length === 0 ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
				className: "meta-dim",
				children: today.empty_footer
			}) : /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { children: today.items.map((item) => /* @__PURE__ */ (0, import_jsx_runtime.jsx)(ItemBlock, { item }, item.id)) }),
			/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "ai-panel",
				children: [
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("label", {
						className: "meta-dim text-xs font-mono tracking-wide uppercase",
						children: "capture · pydantic-ai"
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("textarea", {
						value: note,
						onChange: (e) => setNote(e.target.value),
						placeholder: "Rough note → structured capture (PydanticAI)",
						rows: 2
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
						className: "ai-actions",
						children: [
							/* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", {
								type: "button",
								className: "primary",
								disabled: busy || !note.trim(),
								onClick: () => void submitCapture(),
								children: busy ? "structuring…" : "structure capture"
							}),
							meta ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
								className: "ai-meta",
								children: meta
							}) : null,
							err ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
								className: "ai-meta level-warn",
								children: err
							}) : null
						]
					})
				]
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
				className: "board-card-footer",
				children: today.items.length === 0 ? today.empty_footer : `${today.items.length} items · routine + reminder + capture`
			})
		]
	});
}
function MediaCard({ initial }) {
	const [media, setMedia] = (0, import_react.useState)(initial);
	function setState(state) {
		setMedia((m) => ({
			...m,
			state
		}));
	}
	function next() {
		setMedia((m) => {
			if (!m.queue.length) return m;
			const [head, ...rest] = m.queue;
			const prev = m.current;
			const queue = prev ? [...rest, prev] : rest;
			return {
				...m,
				current: head,
				queue,
				state: m.state === "idle" ? "playing" : m.state
			};
		});
	}
	function stop() {
		setMedia((m) => ({
			...m,
			state: "idle"
		}));
	}
	function toggleCassette() {
		setMedia((m) => ({
			...m,
			cassette: !m.cassette
		}));
	}
	const stateLabel = media.state;
	const track = media.current;
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("section", {
		className: "board-card",
		"data-accent": "peach",
		"aria-label": "media",
		children: [
			/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "flex items-center justify-between gap-2",
				children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("h2", {
					className: "board-card-title",
					"data-accent": "peach",
					children: "media"
				}), media.cassette ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
					className: "cassette-badge",
					children: "cassette on"
				}) : null]
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "flex flex-wrap items-baseline gap-x-3 gap-y-1",
				children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
					className: "font-mono text-xs uppercase tracking-wide text-muted",
					children: stateLabel
				}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
					className: "text-fg",
					children: track ? /* @__PURE__ */ (0, import_jsx_runtime.jsxs)(import_jsx_runtime.Fragment, { children: [track.title, /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", {
						className: "meta-dim",
						children: [" · ", track.artist]
					})] }) : /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
						className: "meta-dim",
						children: "no track"
					})
				})]
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("ul", {
				className: "m-0 list-none p-0 text-sm text-muted",
				children: media.queue.slice(0, 5).map((t, i) => /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("li", {
					className: "item-row py-1",
					children: [
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
							className: "font-mono text-faint tabular mr-2",
							children: i + 1
						}),
						t.title,
						/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", {
							className: "meta-dim",
							children: [" · ", t.artist]
						})
					]
				}, t.id))
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "media-controls",
				children: [
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", {
						type: "button",
						"data-active": media.state === "playing",
						onClick: () => setState("playing"),
						children: "Play"
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", {
						type: "button",
						"data-active": media.state === "paused",
						onClick: () => setState("paused"),
						children: "Pause"
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", {
						type: "button",
						onClick: next,
						children: "Next"
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", {
						type: "button",
						onClick: stop,
						children: "Stop"
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", {
						type: "button",
						"data-active": media.cassette,
						onClick: toggleCassette,
						children: "Cassette"
					})
				]
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "board-card-footer",
				children: [
					media.playlist_label,
					" · ",
					media.speaker,
					" · cassette",
					" ",
					media.cassette ? "on" : "off",
					" · volume ",
					media.volume
				]
			})
		]
	});
}
function LearningCard({ board, onBoard }) {
	const learning = board.learning;
	const pool = learning.pool;
	const windowSize = learning.window_size;
	const [offset, setOffset] = (0, import_react.useState)(0);
	const [ring, setRing] = (0, import_react.useState)(learning.ring);
	const [hovered, setHovered] = (0, import_react.useState)(false);
	const [prompt, setPrompt] = (0, import_react.useState)("");
	const [topic, setTopic] = (0, import_react.useState)("service-rescue");
	const [busy, setBusy] = (0, import_react.useState)(false);
	const [meta, setMeta] = (0, import_react.useState)(null);
	const [err, setErr] = (0, import_react.useState)(null);
	const n = pool.length || 1;
	(0, import_react.useEffect)(() => {
		if (hovered || pool.length <= windowSize) return;
		const id = window.setInterval(() => {
			setOffset((o) => {
				const next = (o + 1) % n;
				if (next === 0) setRing((r) => r + 1);
				return next;
			});
		}, learning.advance_ms);
		return () => window.clearInterval(id);
	}, [
		hovered,
		pool.length,
		windowSize,
		learning.advance_ms,
		n
	]);
	const windowItems = (0, import_react.useMemo)(() => {
		if (!pool.length) return [];
		const out = [];
		for (let i = 0; i < Math.min(windowSize, pool.length); i++) out.push(pool[(offset + i) % pool.length]);
		return out;
	}, [
		pool,
		offset,
		windowSize
	]);
	const i = pool.length ? offset + 1 : 0;
	const j = pool.length ? offset + windowItems.length : 0;
	async function expand() {
		if (!prompt.trim() || busy) return;
		setBusy(true);
		setErr(null);
		try {
			const res = await postLearningExpand(prompt.trim(), topic);
			setMeta(`${res.meta.engine} · ${res.meta.model}`);
			const item = {
				id: `learn-local-${Date.now()}`,
				topic: res.item.topic,
				primary: res.item.primary,
				detail: res.item.detail,
				tags: res.item.tags
			};
			onBoard({
				...board,
				learning: {
					...board.learning,
					pool: [...board.learning.pool, item]
				}
			});
			setPrompt("");
		} catch (e) {
			setErr(e instanceof Error ? e.message : "expand failed");
		} finally {
			setBusy(false);
		}
	}
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("section", {
		className: "board-card learning-card",
		"data-accent": "green",
		"aria-label": "learning",
		onMouseEnter: () => setHovered(true),
		onMouseLeave: () => setHovered(false),
		children: [
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("h2", {
				className: "board-card-title",
				"data-accent": "green",
				children: "learning"
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { children: windowItems.map((item) => /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "item-row",
				children: [
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
						className: "learning-primary",
						children: item.primary
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("p", {
						className: "mt-1 mb-0 text-sm text-muted text-pretty",
						children: item.detail
					}),
					item.tags?.length ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
						className: "mt-1 flex flex-wrap gap-1",
						children: item.tags.map((t) => /* @__PURE__ */ (0, import_jsx_runtime.jsx)(TagChip, { tag: t }, t))
					}) : null
				]
			}, `${item.id}-${offset}`)) }),
			/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "ai-panel",
				children: [
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("label", {
						className: "meta-dim text-xs font-mono tracking-wide uppercase",
						children: "expand sop · pydantic-ai"
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
						className: "flex flex-wrap gap-2",
						children: /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("select", {
							className: "rounded-md border border-border bg-bg px-2 py-2 text-sm text-fg font-mono",
							value: topic,
							onChange: (e) => setTopic(e.target.value),
							children: [
								/* @__PURE__ */ (0, import_jsx_runtime.jsx)("option", {
									value: "allergen-matrix",
									children: "allergen-matrix"
								}),
								/* @__PURE__ */ (0, import_jsx_runtime.jsx)("option", {
									value: "service-rescue",
									children: "service-rescue"
								}),
								/* @__PURE__ */ (0, import_jsx_runtime.jsx)("option", {
									value: "line-opening",
									children: "line-opening"
								})
							]
						})
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("textarea", {
						value: prompt,
						onChange: (e) => setPrompt(e.target.value),
						placeholder: "Seed a kitchen SOP line…",
						rows: 2
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
						className: "ai-actions",
						children: [
							/* @__PURE__ */ (0, import_jsx_runtime.jsx)("button", {
								type: "button",
								className: "primary",
								disabled: busy || !prompt.trim(),
								onClick: () => void expand(),
								style: {
									borderColor: "color-mix(in oklab, var(--color-green) 45%, var(--color-border))",
									background: "color-mix(in oklab, var(--color-green) 12%, var(--color-surface-2))",
									color: "var(--color-green)"
								},
								children: busy ? "expanding…" : "expand with ai"
							}),
							meta ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
								className: "ai-meta",
								children: meta
							}) : null,
							err ? /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
								className: "ai-meta level-warn",
								children: err
							}) : null
						]
					})
				]
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "board-card-footer",
				children: [
					"ring ",
					ring,
					" · ",
					learning.topics_label,
					" · ",
					i,
					"–",
					j,
					" of ",
					pool.length,
					" ↻",
					hovered ? " · paused" : ""
				]
			})
		]
	});
}
function BriefingCard({ briefing }) {
	const [offset, setOffset] = (0, import_react.useState)(0);
	const [ringN, setRingN] = (0, import_react.useState)(briefing.ring_n);
	const [hovered, setHovered] = (0, import_react.useState)(false);
	const pool = briefing.ring;
	const n = pool.length || 1;
	const windowSize = 5;
	(0, import_react.useEffect)(() => {
		if (hovered || pool.length <= windowSize) return;
		const id = window.setInterval(() => {
			setOffset((o) => {
				const next = (o + 1) % n;
				if (next === 0) setRingN((r) => r + 1);
				return next;
			});
		}, briefing.advance_ms);
		return () => window.clearInterval(id);
	}, [
		hovered,
		pool.length,
		briefing.advance_ms,
		n
	]);
	const windowItems = (0, import_react.useMemo)(() => {
		if (!pool.length) return [];
		const out = [];
		for (let i = 0; i < Math.min(windowSize, pool.length); i++) out.push(pool[(offset + i) % pool.length]);
		return out;
	}, [pool, offset]);
	const i = pool.length ? offset + 1 : 0;
	const j = pool.length ? offset + windowItems.length : 0;
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("section", {
		className: "board-card",
		"data-accent": "purple",
		"aria-label": "briefing",
		onMouseEnter: () => setHovered(true),
		onMouseLeave: () => setHovered(false),
		children: [
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("h2", {
				className: "board-card-title",
				"data-accent": "purple",
				children: "briefing"
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
				className: "pin-block",
				children: briefing.pins.map((pin) => /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
					className: "item-row",
					children: [
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
							className: `level-${pin.level}`,
							children: pin.title
						}),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
							className: "mt-1 flex flex-wrap gap-1",
							children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(TagChip, { tag: pin.source })
						}),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)("a", {
							className: "item-url",
							href: pin.url,
							target: "_blank",
							rel: "noreferrer",
							children: pin.url
						})
					]
				}, pin.id))
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { className: "ring-divider" }),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", { children: windowItems.map((item) => /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "item-row",
				children: [
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
						className: `level-${item.level}`,
						children: item.title
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
						className: "mt-1 flex flex-wrap items-center gap-1",
						children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)(TagChip, { tag: item.source }), item.points != null || item.comments != null ? /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", {
							className: "meta-dim font-mono text-xs",
							children: [
								"· ",
								item.points != null ? `${item.points} pts` : "",
								item.points != null && item.comments != null ? " · " : "",
								item.comments != null ? `${item.comments} c` : ""
							]
						}) : null]
					}),
					/* @__PURE__ */ (0, import_jsx_runtime.jsx)("a", {
						className: "item-url",
						href: item.url,
						target: "_blank",
						rel: "noreferrer",
						children: item.url
					})
				]
			}, `${item.id}-${offset}`)) }),
			/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "board-card-footer",
				children: [
					"ring ",
					ringN,
					" · ",
					briefing.sources_label,
					" · ",
					i,
					"–",
					j,
					" of ",
					pool.length,
					" ↻",
					hovered ? " · paused" : ""
				]
			})
		]
	});
}
function MachineCard({ machine }) {
	const diskWarn = machine.disk_pct >= 90;
	const failedWarn = machine.failed_units > 0;
	const netWarn = machine.net === "down";
	const aptWarn = machine.apt_updates > 50;
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("section", {
		className: "board-card",
		"data-accent": "blue",
		"aria-label": "machine",
		children: [
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)("h2", {
				className: "board-card-title",
				"data-accent": "blue",
				children: "machine"
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "machine-strip",
				children: [
					/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", { children: [
						"disk",
						" ",
						/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", {
							className: diskWarn ? "warn-val tabular" : "tabular",
							children: [machine.disk_pct.toFixed(0), "%"]
						})
					] }),
					/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", { children: [
						"free",
						" ",
						/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", {
							className: "tabular",
							children: [machine.free_gib.toFixed(1), " GiB"]
						})
					] }),
					/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", { children: [
						"failed",
						" ",
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
							className: failedWarn ? "warn-val tabular" : "tabular",
							children: machine.failed_units
						})
					] }),
					/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", { children: [
						"net",
						" ",
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
							className: netWarn ? "warn-val" : void 0,
							children: machine.net
						})
					] }),
					/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("span", { children: [
						"apt",
						" ",
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
							className: aptWarn ? "warn-val tabular" : "tabular",
							children: machine.apt_updates
						})
					] })
				]
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "board-card-footer",
				children: [machine.host, machine.warn ? " · attention" : " · quiet"]
			})
		]
	});
}
function CasualBoard() {
	const [board, setBoard] = (0, import_react.useState)(FALLBACK_BOARD);
	const [health, setHealth] = (0, import_react.useState)(null);
	const [loaded, setLoaded] = (0, import_react.useState)(false);
	(0, import_react.useEffect)(() => {
		let cancelled = false;
		(async () => {
			const [b, h] = await Promise.all([fetchBoard(), fetchHealth()]);
			if (cancelled) return;
			setBoard(b);
			setHealth(h);
			setLoaded(true);
		})();
		return () => {
			cancelled = true;
		};
	}, []);
	return /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
		className: "app-shell",
		children: [
			/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "mb-1 flex flex-wrap items-baseline justify-between gap-2",
				children: [/* @__PURE__ */ (0, import_jsx_runtime.jsx)("h1", {
					className: "m-0 font-mono text-sm font-medium tracking-wide text-fg uppercase",
					children: "Casual Board"
				}), /* @__PURE__ */ (0, import_jsx_runtime.jsx)("span", {
					className: "font-mono text-xs text-faint",
					children: loaded ? health ? "api · pydantic + pydantic-ai" : "local seed" : "loading…"
				})]
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsx)(HeaderBar, {
				header: board.header,
				health
			}),
			/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
				className: "board-grid",
				children: [/* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
					className: "board-col board-col-left flex flex-col gap-3.5",
					children: [
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)(TodayCard, {
							board,
							onBoard: setBoard
						}),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)(MediaCard, { initial: board.media }),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
							className: "hidden min-[1100px]:block",
							children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(MachineCard, { machine: board.machine })
						})
					]
				}), /* @__PURE__ */ (0, import_jsx_runtime.jsxs)("div", {
					className: "board-col board-col-right flex flex-col gap-3.5",
					children: [
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)(LearningCard, {
							board,
							onBoard: setBoard
						}),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)(BriefingCard, { briefing: board.briefing }),
						/* @__PURE__ */ (0, import_jsx_runtime.jsx)("div", {
							className: "min-[1100px]:hidden",
							children: /* @__PURE__ */ (0, import_jsx_runtime.jsx)(MachineCard, { machine: board.machine })
						})
					]
				})]
			})
		]
	});
}
function Home() {
	return /* @__PURE__ */ (0, import_jsx_runtime.jsx)(CasualBoard, {});
}
//#endregion
export { Home as component };
