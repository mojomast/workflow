/*
 * rizzstack-observatory live panel: fleet -> bee -> streaming turn tail.
 *
 * Data sources (same-origin proxy pattern; see
 * contrib/rizzstack-observatory/README.md):
 *   GET /obs-snapshot  -> collector point-in-time fleet document
 *   GET /obs-events    -> events bridge Server-Sent Events stream
 *
 * The panel only ever speaks the rails vocabulary (dotted event kinds and
 * lifecycle state labels); the bridge translates launcher kinds on the wire,
 * so this file upgrades to rails rendering without a rewrite.
 *
 * The helpers below the fold are pure and exported for the stress harness;
 * the DOM layer mounts itself and builds its skeleton when the serving shell
 * does not provide one.
 */
(function (root) {
  "use strict";

  var UNKNOWN_KIND = "event.other";

  // Display-side copy of the bridge mapping table: launcher spellings are
  // tolerated here too, but the wire format is already the rails vocabulary.
  var KIND_MAP = {
    attempt_started: "bee.started",
    "attempt.start": "bee.started",
    bee_started: "bee.started",
    started: "bee.started",
    attempt_finished: "bee.finished",
    attempt_completed: "bee.finished",
    bee_finished: "bee.finished",
    done: "bee.finished",
    attempt_state: "bee.state",
    state_changed: "bee.state",
    phase_changed: "bee.state",
    state: "bee.state",
    turn_started: "turn.started",
    "turn.start": "turn.started",
    turn_finished: "turn.finished",
    "turn.finish": "turn.finished",
    turn_complete: "turn.finished",
    tool_update: "tool.progress",
    "tool.update": "tool.progress",
    tool_progress: "tool.progress",
    tool_call: "tool.progress",
    tool_result: "tool.done",
    "tool.done": "tool.done",
    tool_finished: "tool.done",
    tool_output: "tool.done",
    bee_note: "bee.note",
    note: "bee.note",
    log: "bee.note",
    heartbeat: "bee.note",
    bee_error: "bee.error",
    error: "bee.error",
    failure: "bee.error"
  };

  var RAILS_KINDS = [
    "bee.started",
    "bee.state",
    "bee.note",
    "bee.error",
    "bee.finished",
    "turn.started",
    "turn.finished",
    "tool.progress",
    "tool.done",
    "event.other"
  ];

  var WINDOW_ROWS = 400;     // rendered row cap per tail (windowing)
  var MAX_TAIL_EVENTS = 5000; // in-memory ring per bee
  var RECONNECT_DELAY_MS = 3000;

  function railsKindOf(value) {
    if (typeof value !== "string") {
      return UNKNOWN_KIND;
    }
    var label = value.trim().toLowerCase();
    if (RAILS_KINDS.indexOf(label) !== -1) {
      return label; // already the rails vocabulary
    }
    if (Object.prototype.hasOwnProperty.call(KIND_MAP, label)) {
      return KIND_MAP[label];
    }
    var folded = label.replace(/-/g, "_").replace(/ /g, "_");
    return Object.prototype.hasOwnProperty.call(KIND_MAP, folded) ? KIND_MAP[folded] : UNKNOWN_KIND;
  }

  /* Tolerant client-side normalization: the bridge usually normalizes on the
   * wire, but a direct raw-kind stream still renders. */
  function normalizeEvent(raw) {
    var event = raw && typeof raw === "object" && !Array.isArray(raw) ? raw : {};
    var kind = railsKindOf(event.kind);
    return {
      seq: typeof event.seq === "number" ? event.seq : 0,
      ts: typeof event.ts === "number" ? event.ts : 0,
      kind: kind,
      rawKind: typeof event.raw_kind === "string" ? event.raw_kind : "",
      bee: event.bee || null,
      turn: event.turn || null,
      tool: event.tool || null,
      state: event.state || null,
      detail: typeof event.detail === "string" ? event.detail : "",
      payload: event.payload || {}
    };
  }

  /* Collapse contract (mirrored in tests/test_obs_events_bridge.py): adjacent
   * tool progress updates for the same (turn, tool) merge into one row; any
   * other kind, a turn change or a tool change starts a new row. 2000 updates
   * in 8 runs therefore collapse to 8 rows. */
  function collapseToolUpdates(events) {
    var rows = [];
    for (var index = 0; index < events.length; index++) {
      var event = events[index];
      var kind = railsKindOf(event.kind);
      var last = rows.length ? rows[rows.length - 1] : null;
      if (
        kind === "tool.progress" &&
        last &&
        last.row === "tool" &&
        last.turn === (event.turn || null) &&
        last.tool === (event.tool || null)
      ) {
        last.count += 1;
        last.lastSeq = event.seq || last.lastSeq;
        if (event.detail) {
          last.lastDetail = event.detail;
        }
        continue;
      }
      if (kind === "tool.progress") {
        rows.push({
          row: "tool",
          kind: kind,
          turn: event.turn || null,
          tool: event.tool || null,
          count: 1,
          firstSeq: event.seq || 0,
          lastSeq: event.seq || 0,
          lastDetail: event.detail || null
        });
      } else {
        rows.push({ row: "event", kind: kind, seq: event.seq || 0, event: event });
      }
    }
    return rows;
  }

  /* Windowing contract (mirrored in tests/test_obs_events_bridge.py): keep
   * the last ``cap`` rows, order preserved. */
  function applyWindow(rows, cap) {
    if (!cap || rows.length <= cap) {
      return rows;
    }
    return rows.slice(rows.length - cap);
  }

  function clockOf(ts) {
    if (!ts) {
      return "--:--:--";
    }
    var date = new Date(ts);
    function pad(n) {
      return (n < 10 ? "0" : "") + n;
    }
    return pad(date.getHours()) + ":" + pad(date.getMinutes()) + ":" + pad(date.getSeconds());
  }

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) {
      node.className = className;
    }
    if (text !== undefined && text !== null) {
      node.textContent = String(text);
    }
    return node;
  }

  // ------------------------------------------------------------------ panel

  function mount() {
    var panel = document.getElementById("obs-panel") || buildSkeleton();
    var refs = {
      status: panel.querySelector("#obs-status"),
      fleet: panel.querySelector("#obs-fleet"),
      beeName: panel.querySelector("#obs-bee-name"),
      filters: panel.querySelector("#obs-filters"),
      tail: panel.querySelector("#obs-tail"),
      reconnect: panel.querySelector("#obs-reconnect")
    };

    var state = {
      selected: null,
      fleet: [],
      tails: Object.create(null), // bee -> {events: [], at: 0}
      enabled: {},
      lastSeq: 0,
      stream: null,
      clockStart: Date.now(),
      seenMinute: 0
    };
    RAILS_KINDS.forEach(function (kind) {
      state.enabled[kind] = true;
    });

    renderFilters(refs, state);
    if (refs.reconnect) {
      refs.reconnect.addEventListener("click", function () {
        openStream(refs, state);
      });
    }
    setStatus(refs, state, "connecting");
    loadSnapshot(refs, state);
    openStream(refs, state);
    setInterval(function () {
      if (Date.now() - state.clockStart >= 60000) {
        state.clockStart = Date.now();
        state.seenMinute = 0;
      }
      renderFleet(refs, state);
    }, 5000);
    return state;
  }

  function buildSkeleton() {
    var panel = el("section", "obs-panel");
    panel.id = "obs-panel";
    var head = el("header", "obs-head");
    var status = el("div", "obs-status");
    status.id = "obs-status";
    var reconnect = el("button", "obs-reconnect", "reconnect");
    reconnect.id = "obs-reconnect";
    reconnect.type = "button";
    head.appendChild(status);
    head.appendChild(reconnect);
    var body = el("div", "obs-body");
    var fleet = el("aside", "obs-fleet");
    fleet.id = "obs-fleet";
    var main = el("main", "obs-bee");
    var beeName = el("h2", "obs-bee-name", "select a bee");
    beeName.id = "obs-bee-name";
    var filters = el("div", "obs-filters");
    filters.id = "obs-filters";
    var tail = el("div", "obs-tail");
    tail.id = "obs-tail";
    main.appendChild(beeName);
    main.appendChild(filters);
    main.appendChild(tail);
    body.appendChild(fleet);
    body.appendChild(main);
    panel.appendChild(head);
    panel.appendChild(body);
    (document.body || document.documentElement).appendChild(panel);
    return panel;
  }

  function setStatus(refs, state, label) {
    if (!refs.status) {
      return;
    }
    refs.status.textContent = "";
    refs.status.appendChild(el("span", "obs-badge obs-badge-" + label.replace(/[^a-z]+/g, "-"), label));
    refs.status.appendChild(
      el("span", "obs-cursor", " cursor " + state.lastSeq + " - " + state.seenMinute + " ev/min")
    );
  }

  function loadSnapshot(refs, state) {
    if (typeof fetch !== "function") {
      return;
    }
    fetch("/obs-snapshot", { headers: { Accept: "application/json" } })
      .then(function (response) {
        return response.ok ? response.json() : null;
      })
      .then(function (doc) {
        if (!doc) {
          return;
        }
        var attempts = doc && doc.fleet && doc.fleet.attempts;
        state.fleet = Array.isArray(attempts) ? attempts : [];
        state.fleet.forEach(function (row) {
          ensureTail(state, row.attempt_id);
        });
        if (!state.selected && state.fleet.length) {
          selectBee(refs, state, state.fleet[0].attempt_id);
        }
        renderFleet(refs, state);
      })
      .catch(function () {
        /* The collector route is optional here; the stream still populates. */
      });
  }

  function streamUrl(cursor) {
    return cursor ? "/obs-events?cursor=" + encodeURIComponent(cursor) : "/obs-events";
  }

  function openStream(refs, state) {
    if (typeof EventSource !== "function") {
      setStatus(refs, state, "stream unsupported");
      return;
    }
    if (state.stream) {
      state.stream.close();
    }
    var source = new EventSource(streamUrl(state.lastSeq > 0 ? state.lastSeq : null));
    state.stream = source;

    source.addEventListener("hello", function (signal) {
      var data = parse(signal);
      if (data && state.lastSeq === 0) {
        state.lastSeq = data.cursor || 0;
      }
      setStatus(refs, state, "live");
    });
    source.addEventListener("reset", function () {
      /* Gap: drop stream state, refetch the snapshot, reopen without a cursor. */
      state.lastSeq = 0;
      if (state.stream) {
        state.stream.close();
      }
      setStatus(refs, state, "resyncing");
      loadSnapshot(refs, state);
      setTimeout(function () {
        openStream(refs, state);
      }, 250);
    });
    source.addEventListener("bye", function () {
      setStatus(refs, state, "stream ended");
      if (state.stream) {
        state.stream.close();
        state.stream = null;
      }
    });
    source.onerror = function () {
      /* The browser retries automatically and resends Last-Event-ID. */
      setStatus(refs, state, "reconnecting");
    };
    RAILS_KINDS.forEach(function (kind) {
      source.addEventListener(kind, function (signal) {
        ingest(refs, state, signal);
      });
    });
    source.addEventListener(UNKNOWN_KIND, function (signal) {
      ingest(refs, state, signal);
    });
  }

  function parse(signal) {
    try {
      return JSON.parse(signal.data);
    } catch (err) {
      return null;
    }
  }

  function ingest(refs, state, signal) {
    var raw = parse(signal);
    if (!raw) {
      return;
    }
    if (signal.lastEventId) {
      state.lastSeq = Math.max(state.lastSeq, Number(signal.lastEventId) || 0);
    }
    var event = normalizeEvent(raw);
    var bee = event.bee || "_unattached";
    var tail = ensureTail(state, bee);
    tail.events.push(event);
    if (tail.events.length > MAX_TAIL_EVENTS) {
      tail.events.splice(0, tail.events.length - MAX_TAIL_EVENTS);
    }
    tail.at = Date.now();
    state.seenMinute += 1;
    if (state.fleet.every(function (row) {
      return row.attempt_id !== bee;
    })) {
      state.fleet.push({ attempt_id: bee, state: event.state || "unknown", live_only: true });
    }
    if (bee === state.selected) {
      renderTail(refs, state);
    }
    setStatus(refs, state, "live");
  }

  function ensureTail(state, bee) {
    if (!state.tails[bee]) {
      state.tails[bee] = { events: [], at: 0 };
    }
    return state.tails[bee];
  }

  function selectBee(refs, state, bee) {
    state.selected = bee;
    if (refs.beeName) {
      refs.beeName.textContent = bee;
    }
    renderFleet(refs, state);
    renderTail(refs, state);
  }

  function renderFleet(refs, state) {
    if (!refs.fleet) {
      return;
    }
    var list = refs.fleet.querySelector("ul");
    if (!list) {
      list = el("ul", "obs-fleet-list");
      refs.fleet.appendChild(el("h2", "obs-side-title", "fleet"));
      refs.fleet.appendChild(list);
    }
    list.textContent = "";
    if (!state.fleet.length) {
      list.appendChild(el("li", "obs-empty", "no attempts yet - waiting for the stream"));
      return;
    }
    state.fleet.forEach(function (row) {
      var bee = row.attempt_id || "unknown";
      var item = el("li", "obs-fleet-row" + (bee === state.selected ? " is-selected" : ""));
      item.appendChild(el("span", "obs-badge obs-state-" + String(row.state || "unknown"), String(row.state || "unknown")));
      item.appendChild(el("span", "obs-bee-id", bee));
      if (row.repo) {
        item.appendChild(el("span", "obs-dim", String(row.repo)));
      }
      var tail = state.tails[bee];
      if (tail && tail.at) {
        item.appendChild(el("span", "obs-dim", clockOf(tail.at)));
      }
      item.addEventListener("click", function () {
        selectBee(refs, state, bee);
      });
      list.appendChild(item);
    });
  }

  function renderFilters(refs, state) {
    if (!refs.filters) {
      return;
    }
    refs.filters.textContent = "";
    RAILS_KINDS.forEach(function (kind) {
      var chip = el("label", "obs-chip" + (state.enabled[kind] ? " is-on" : " is-off"));
      var box = document.createElement("input");
      box.type = "checkbox";
      box.checked = state.enabled[kind];
      box.addEventListener("change", function () {
        state.enabled[kind] = box.checked;
        chip.className = "obs-chip" + (box.checked ? " is-on" : " is-off");
        renderTail(refs, state);
      });
      chip.appendChild(box);
      chip.appendChild(el("span", null, kind));
      refs.filters.appendChild(chip);
    });
  }

  function renderTail(refs, state) {
    if (!refs.tail) {
      return;
    }
    var tail = state.selected ? state.tails[state.selected] : null;
    refs.tail.textContent = "";
    if (!state.selected) {
      refs.tail.appendChild(el("p", "obs-empty", "select a bee from the fleet"));
      return;
    }
    if (!tail || !tail.events.length) {
      refs.tail.appendChild(el("p", "obs-empty", "no events yet for " + state.selected));
      return;
    }
    var rows = collapseToolUpdates(tail.events);
    var groups = [];
    var current = null;
    rows.forEach(function (row) {
      var turnKey = row.row === "tool" ? row.turn : (row.event && row.event.turn) || null;
      if (!current || current.turn !== turnKey) {
        current = { turn: turnKey, rows: [] };
        groups.push(current);
      }
      current.rows.push(row);
    });
    var shown = applyWindow(groups, WINDOW_ROWS);
    shown.forEach(function (group) {
      var block = el("section", "obs-turn");
      block.appendChild(
        el("h3", "obs-turn-title", "turn " + (group.turn || "unattached"))
      );
      group.rows.forEach(function (row) {
        if (!state.enabled[row.kind]) {
          return;
        }
        block.appendChild(rowNode(row));
      });
      refs.tail.appendChild(block);
    });
    refs.tail.scrollTop = refs.tail.scrollHeight;
  }

  function rowNode(row) {
    if (row.row === "tool") {
      var collapsed = el("div", "obs-row obs-row-tool");
      collapsed.appendChild(el("span", "obs-kind obs-kind-tool-progress", "tool.progress"));
      collapsed.appendChild(el("span", "obs-tool", row.tool || "unknown tool"));
      collapsed.appendChild(el("span", "obs-count", "x" + row.count));
      if (row.lastDetail) {
        collapsed.appendChild(el("span", "obs-detail", row.lastDetail));
      }
      collapsed.appendChild(el("span", "obs-dim", "seq " + row.firstSeq + "-" + row.lastSeq));
      return collapsed;
    }
    var event = row.event || {};
    var line = el("div", "obs-row obs-row-" + row.kind.replace(/\./g, "-"));
    line.appendChild(el("span", "obs-kind obs-kind-" + row.kind.replace(/\./g, "-"), row.kind));
    if (event.state) {
      line.appendChild(el("span", "obs-badge obs-state-" + String(event.state), String(event.state)));
    }
    if (event.tool) {
      line.appendChild(el("span", "obs-tool", String(event.tool)));
    }
    if (event.detail) {
      line.appendChild(el("span", "obs-detail", event.detail));
    }
    line.appendChild(el("span", "obs-dim", clockOf(event.ts) + " seq " + event.seq));
    return line;
  }

  var api = {
    UNKNOWN_KIND: UNKNOWN_KIND,
    KIND_MAP: KIND_MAP,
    RAILS_KINDS: RAILS_KINDS,
    WINDOW_ROWS: WINDOW_ROWS,
    MAX_TAIL_EVENTS: MAX_TAIL_EVENTS,
    RECONNECT_DELAY_MS: RECONNECT_DELAY_MS,
    railsKindOf: railsKindOf,
    normalizeEvent: normalizeEvent,
    collapseToolUpdates: collapseToolUpdates,
    applyWindow: applyWindow,
    mount: mount
  };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
  root.rizzstackObservatory = api;

  if (typeof document !== "undefined") {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", mount);
    } else {
      mount();
    }
  }
})(typeof window !== "undefined" ? window : this);
