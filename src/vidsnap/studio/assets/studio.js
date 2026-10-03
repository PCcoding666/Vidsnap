(function () {
  "use strict";

  var DATA = JSON.parse(document.getElementById("vidsnap-studio-data").textContent);
  var NOT_RECORDED = "\u672a\u8bb0\u5f55 \u00b7 not recorded";
  var LANE_NAMES = ["input", "model", "tools", "verifier"];
  var LANE_LABELS = { input: "Input", model: "Model", tools: "Tools", verifier: "Verifier" };

  function make(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }

  function clear(node) {
    while (node.firstChild) node.removeChild(node.firstChild);
  }

  function notRecorded() {
    return make("span", "not-recorded", NOT_RECORDED);
  }

  function syntheticBadge() {
    return make("span", "synthetic-badge", "SYNTHETIC");
  }

  function statusText(passed) {
    if (passed === true) return "passed";
    if (passed === false) return "failed";
    return null;
  }

  function panelBody(name) {
    return document.querySelector('[data-panel-body="' + name + '"]');
  }

  /* ---------- tabs ---------- */

  function tabsIn(tablist) {
    return Array.prototype.slice.call(tablist.querySelectorAll('[role="tab"]'));
  }

  function selectTab(tablist, tab) {
    resetTrialContext();
    tabsIn(tablist).forEach(function (other) {
      var selected = other === tab;
      other.setAttribute("aria-selected", selected ? "true" : "false");
      other.tabIndex = selected ? 0 : -1;
      var panel = document.getElementById(other.getAttribute("aria-controls"));
      if (panel) panel.hidden = !selected;
    });
  }

  function wireTablist(tablist) {
    var tabs = tabsIn(tablist);
    tabs.forEach(function (tab) {
      tab.addEventListener("click", function () {
        selectTab(tablist, tab);
      });
      tab.addEventListener("keydown", function (event) {
        var index = tabs.indexOf(tab);
        var target = null;
        if (event.key === "ArrowRight") target = tabs[(index + 1) % tabs.length];
        else if (event.key === "ArrowLeft") target = tabs[(index - 1 + tabs.length) % tabs.length];
        else if (event.key === "Home") target = tabs[0];
        else if (event.key === "End") target = tabs[tabs.length - 1];
        if (target) {
          event.preventDefault();
          selectTab(tablist, target);
          target.focus();
        }
      });
    });
  }

  /* ---------- overlays (dialogs) with focus return ---------- */

  var focusStack = [];

  function openOverlay(wrap, trigger) {
    wrap.hidden = false;
    focusStack.push(trigger || document.activeElement);
    var focusable = wrap.querySelector("button");
    if (focusable) focusable.focus();
  }

  function closeOverlay(wrap) {
    wrap.hidden = true;
    var trigger = focusStack.pop();
    if (trigger && typeof trigger.focus === "function") trigger.focus();
  }

  function resetTrialContext() {
    // Navigation-triggered close: never restore focus into the drawer that is
    // about to hide; the activating tab or version select keeps focus.
    var trialWrap = document.getElementById("trial-dialog-wrap");
    if (!trialWrap.hidden) {
      trialWrap.hidden = true;
      focusStack.pop();
    }
    dialogState = null;
    drawerState = null;
    document.getElementById("trial-drawer").hidden = true;
  }

  /* ---------- iteration workspace ---------- */

  var diffIndex = 1;

  function diffRange(iteration) {
    return iteration.versions.length - 1;
  }

  function updateDiffLabel(iteration) {
    var label = document.getElementById("diff-label");
    clear(label);
    if (diffRange(iteration) < 1) {
      label.appendChild(notRecorded());
      return;
    }
    diffIndex = Math.min(Math.max(diffIndex, 1), diffRange(iteration));
    label.textContent =
      iteration.versions[diffIndex - 1].version + " \u2192 " + iteration.versions[diffIndex].version;
  }

  function renderDiffModal() {
    var iteration = DATA.iteration;
    if (!iteration || diffRange(iteration) < 1) return;
    var before = iteration.versions[diffIndex - 1];
    var after = iteration.versions[diffIndex];
    document.getElementById("diff-dialog-title").textContent =
      before.version + " \u2192 " + after.version;
    var body = document.getElementById("diff-body");
    clear(body);
    [before, after].forEach(function (version) {
      var side = make("div", "diff-side");
      side.appendChild(make("h3", null, version.version));
      side.appendChild(make("p", null, version.summary));
      if (version.prompt) side.appendChild(make("pre", null, version.prompt));
      else {
        var missing = make("p");
        missing.appendChild(notRecorded());
        side.appendChild(missing);
      }
      body.appendChild(side);
    });
  }

  function renderVersionList(iteration) {
    var list = document.getElementById("version-list");
    clear(list);
    iteration.versions.forEach(function (version) {
      var card = make("div", "version-card");
      card.appendChild(make("h3", null, version.version));
      card.appendChild(make("p", null, version.summary));
      var sha = make("p");
      sha.appendChild(document.createTextNode("prompt_sha256: "));
      sha.appendChild(version.prompt_sha256 ? make("code", null, version.prompt_sha256) : notRecorded());
      card.appendChild(sha);
      if (version.prompt) card.appendChild(make("pre", null, version.prompt));
      else {
        var missing = make("p");
        missing.appendChild(notRecorded());
        card.appendChild(missing);
      }
      list.appendChild(card);
    });
  }

  function selectedVersion() {
    return document.getElementById("version-select").value;
  }

  function fillVersionSelect(iteration) {
    var select = document.getElementById("version-select");
    clear(select);
    iteration.versions.forEach(function (version) {
      var option = document.createElement("option");
      option.value = version.version;
      option.textContent = version.version;
      select.appendChild(option);
    });
    select.value = iteration.versions[iteration.versions.length - 1].version;
    select.addEventListener("change", function () {
      resetTrialContext();
      renderMatrices(DATA.iteration);
    });
  }

  function renderMatrices(iteration) {
    renderMatrix(document.getElementById("eval-matrix"), iteration.eval_cases, false);
    renderMatrix(document.getElementById("heldout-matrix"), iteration.held_out_cases, true);
  }

  function renderMatrix(container, groups, heldOut) {
    clear(container);
    var version = selectedVersion();
    var table = make("table", "matrix");
    var head = make("tr");
    head.appendChild(make("th", null, "Case"));
    head.appendChild(make("th", null, "Trials at " + version));
    table.appendChild(head);
    groups.forEach(function (group) {
      var row = make("tr");
      row.appendChild(make("td", null, group.case_id + (heldOut ? " (held-out)" : "")));
      var cellTd = make("td");
      var entry = null;
      group.entries.forEach(function (candidate) {
        if (candidate.version === version) entry = candidate;
      });
      if (!entry || !entry.trials.length) {
        cellTd.appendChild(notRecorded());
      } else {
        var statuses = entry.trials.map(function (trial) {
          return statusText(trial.verifier.passed);
        });
        var overall = "not-recorded";
        if (statuses.indexOf("failed") >= 0) overall = "failed";
        else if (statuses.indexOf("passed") >= 0) overall = "passed";
        var button = make("button", "cell");
        button.type = "button";
        button.setAttribute("data-cell", group.case_id + ":" + version);
        button.setAttribute("data-status", overall);
        var summary =
          entry.trials.length +
          " trial(s): " +
          statuses
            .map(function (status) {
              return status || "not recorded";
            })
            .join(", ");
        button.setAttribute("aria-label", "version " + version + " case " + group.case_id + ", " + summary);
        button.appendChild(make("span", "cell-name", group.case_id));
        button.appendChild(make("span", "cell-status", summary));
        button.addEventListener("click", function () {
          openDrawer(group, version, entry.trials);
        });
        cellTd.appendChild(button);
      }
      row.appendChild(cellTd);
      table.appendChild(row);
    });
    container.appendChild(table);
  }

  /* ---------- trial drawer and dialog ---------- */

  var drawerState = null;
  var dialogState = null;

  function openDrawer(group, version, trials) {
    drawerState = { group: group, version: version, trials: trials };
    var list = document.getElementById("trial-list");
    clear(list);
    trials.forEach(function (trial, index) {
      var item = make("li");
      var button = make("button");
      button.type = "button";
      var status = statusText(trial.verifier.passed);
      button.textContent = trial.trial_id + " \u2014 " + (status || NOT_RECORDED);
      button.addEventListener("click", function () {
        openTrialDialog(index, button);
      });
      item.appendChild(button);
      list.appendChild(item);
    });
    var drawer = document.getElementById("trial-drawer");
    drawer.hidden = false;
    var first = list.querySelector("button");
    if (first) first.focus();
  }

  function openTrialDialog(index, trigger) {
    if (!drawerState) return;
    dialogState = { index: index };
    renderTrialDialog();
    openOverlay(document.getElementById("trial-dialog-wrap"), trigger);
  }

  function renderTrialDialog() {
    var trial = drawerState.trials[dialogState.index];
    document.getElementById("trial-dialog-title").textContent =
      drawerState.version + " / " + drawerState.group.case_id + " / " + trial.trial_id;
    renderAnswer(trial);
    renderEvidence(trial);
    renderTracePanel(trial);
    renderVerifier(trial);
  }

  function renderAnswer(trial) {
    var body = panelBody("answer");
    clear(body);
    if (!trial.answer.claims.length) {
      body.appendChild(notRecorded());
      return;
    }
    trial.answer.claims.forEach(function (claim) {
      var div = make("div", "claim");
      div.appendChild(make("p", null, claim.text || NOT_RECORDED));
      div.appendChild(
        make(
          "p",
          null,
          "evidence: " + (claim.evidence_ids.length ? claim.evidence_ids.join(", ") : NOT_RECORDED)
        )
      );
      body.appendChild(div);
    });
  }

  function renderEvidence(trial) {
    var body = panelBody("evidence");
    clear(body);
    if (!trial.evidence.items.length) {
      body.appendChild(notRecorded());
      return;
    }
    trial.evidence.items.forEach(function (item) {
      var div = make("div", "evidence-item");
      div.appendChild(
        make("p", null, (item.evidence_id || NOT_RECORDED) + " \u00b7 " + (item.modality || NOT_RECORDED))
      );
      var spanText =
        (item.start_seconds === null ? NOT_RECORDED : item.start_seconds + "s") +
        " \u2013 " +
        (item.end_seconds === null ? NOT_RECORDED : item.end_seconds + "s");
      div.appendChild(make("p", null, spanText));
      if (item.content_preview) div.appendChild(make("p", null, item.content_preview));
      body.appendChild(div);
    });
  }

  function renderTracePanel(trial) {
    var body = panelBody("trace");
    clear(body);
    var panel = trial.trace_panel;
    body.appendChild(renderTimeline(panel));
    body.appendChild(renderBudget(panel));
    body.appendChild(renderEventList(panel));
  }

  function eventLabel(item, lane) {
    if (
      lane === "tools" &&
      item.event_type.indexOf("tool.call") === 0 &&
      item.payload &&
      typeof item.payload.name === "string" &&
      item.payload.name
    ) {
      return item.payload.name;
    }
    return item.event_type;
  }

  function timelineSpan(item) {
    // Trace semantics: offset_ms is the completion time; duration_ms is the span.
    if (typeof item.offset_ms !== "number") return null;
    var end = item.offset_ms;
    var start =
      typeof item.duration_ms === "number" ? Math.max(0, item.offset_ms - item.duration_ms) : end;
    return { start: start, end: end };
  }

  function renderTimeline(panel) {
    var timeline = make("div", "timeline");
    var maxEnd = 0;
    panel.items.forEach(function (item) {
      var span = timelineSpan(item);
      if (span && span.end > maxEnd) maxEnd = span.end;
    });
    var total = 0;
    if (typeof panel.duration_ms === "number" && panel.duration_ms > 0) total = panel.duration_ms;
    if (maxEnd > total) total = maxEnd;
    LANE_NAMES.forEach(function (lane) {
      var row = make("div", "timeline-lane");
      row.setAttribute("data-lane", lane);
      row.appendChild(make("div", "lane-label", LANE_LABELS[lane]));
      var track = make("div", "lane-track");
      var items = panel.lanes[lane];
      items.forEach(function (item, index) {
        var classes = "event-block lane-" + lane;
        if (item.status === "failed") classes += " status-failed";
        var block = make("div", classes);
        var label = eventLabel(item, lane);
        if (typeof item.duration_ms === "number") label += " \u00b7 " + item.duration_ms + " ms";
        var span = timelineSpan(item);
        if (total > 0 && span) {
          block.style.left = (span.start / total) * 100 + "%";
          block.style.width = Math.max(((span.end - span.start) / total) * 100, 1.5) + "%";
        } else {
          var slice = 100 / Math.max(items.length, 1);
          block.style.left = index * slice + "%";
          block.style.width = slice + "%";
        }
        block.textContent = label;
        block.title =
          "#" + item.sequence + " " + item.event_type + " (" + item.phase +
          (item.status ? ", " + item.status : "") + ")";
        track.appendChild(block);
      });
      row.appendChild(track);
      timeline.appendChild(row);
    });
    return timeline;
  }

  function renderBudget(panel) {
    var budget = panel.budget;
    var wrap = make("div", "budget");
    ["model_calls", "evidence_frames", "iterations", "runtime_ms"].forEach(function (name) {
      var counter = budget[name];
      var line = make("p");
      line.appendChild(document.createTextNode(name + ": "));
      line.appendChild(counter.used === null ? notRecorded() : make("span", null, String(counter.used)));
      line.appendChild(document.createTextNode(" / "));
      line.appendChild(counter.limit === null ? notRecorded() : make("span", null, String(counter.limit)));
      wrap.appendChild(line);
    });
    return wrap;
  }

  function renderEventList(panel) {
    var table = make("table", "event-list");
    var head = make("tr");
    ["#", "event", "lane", "phase", "payload", "status", "offset_ms", "duration_ms"].forEach(function (label) {
      head.appendChild(make("th", null, label));
    });
    table.appendChild(head);
    panel.items.forEach(function (item) {
      var row = make("tr");
      row.appendChild(make("td", null, String(item.sequence)));
      row.appendChild(make("td", null, item.event_type));
      row.appendChild(make("td", null, item.lane));
      row.appendChild(make("td", null, item.phase));
      var payloadCell = make("td");
      if (item.payload && Object.keys(item.payload).length) {
        payloadCell.appendChild(make("span", null, JSON.stringify(item.payload)));
      } else {
        payloadCell.appendChild(notRecorded());
      }
      row.appendChild(payloadCell);
      row.appendChild(make("td", null, item.status || NOT_RECORDED));
      var offset = make("td");
      offset.appendChild(typeof item.offset_ms === "number" ? make("span", null, String(item.offset_ms)) : notRecorded());
      row.appendChild(offset);
      var duration = make("td");
      duration.appendChild(
        typeof item.duration_ms === "number" ? make("span", null, String(item.duration_ms)) : notRecorded()
      );
      row.appendChild(duration);
      table.appendChild(row);
    });
    return table;
  }

  function renderVerifier(trial) {
    var body = panelBody("verifier");
    clear(body);
    var verifier = trial.verifier;
    [
      ["terminal_state", verifier.terminal_state],
      ["passed", verifier.passed]
    ].forEach(function (pair) {
      var line = make("p");
      line.appendChild(document.createTextNode(pair[0] + ": "));
      if (pair[1] === null || pair[1] === undefined) line.appendChild(notRecorded());
      else {
        var tone = "";
        if (pair[1] === true) tone = "status-passed";
        if (pair[1] === false) tone = "status-failed";
        line.appendChild(make("span", tone, String(pair[1])));
      }
      body.appendChild(line);
    });
    var gates = make("p");
    gates.appendChild(document.createTextNode("failed_gates: "));
    if (trial.verifier.provenance === "not_recorded" || verifier.failed_gates === null) {
      gates.appendChild(notRecorded());
    } else if (verifier.failed_gates.length) {
      gates.appendChild(make("span", "status-failed", verifier.failed_gates.join(", ")));
    } else {
      gates.appendChild(make("span", "status-passed", "none (0)"));
    }
    body.appendChild(gates);
  }

  /* ---------- exploration workspace ---------- */

  function renderExploration() {
    var exploration = DATA.exploration;
    if (!exploration) return;
    var statement = document.getElementById("problem-statement");
    clear(statement);
    statement.appendChild(make("p", null, exploration.problem.statement));
    if (exploration.problem.constraints.length) {
      var list = make("ul", "constraints");
      exploration.problem.constraints.forEach(function (constraint) {
        list.appendChild(make("li", null, constraint));
      });
      statement.appendChild(list);
    }
    var cards = document.getElementById("approach-cards");
    clear(cards);
    exploration.approaches.forEach(function (approach) {
      cards.appendChild(renderApproachCard(approach));
    });
    fillEvalTable(exploration);
  }

  function renderApproachCard(approach) {
    var card = make("div", "approach-card");
    var heading = make("h3");
    heading.appendChild(document.createTextNode(approach.label + " "));
    if (approach.synthetic) heading.appendChild(syntheticBadge());
    card.appendChild(heading);
    card.appendChild(
      make(
        "p",
        null,
        "max_model_calls: " + approach.harness.max_model_calls +
          " \u00b7 max_tool_calls: " + approach.harness.max_tool_calls
      )
    );
    if (approach.harness.tools.length) {
      card.appendChild(make("p", null, "tools: " + approach.harness.tools.join(", ")));
    }
    var sha = make("p");
    sha.appendChild(document.createTextNode("prompt_sha256: "));
    sha.appendChild(approach.prompt_sha256 ? make("code", null, approach.prompt_sha256) : notRecorded());
    card.appendChild(sha);
    var trialLine = make("p");
    trialLine.appendChild(document.createTextNode("trials: "));
    approach.trials.forEach(function (trial) {
      var status = statusText(trial.verifier.passed);
      trialLine.appendChild(make("code", null, trial.trial_id + "=" + (status || NOT_RECORDED) + " "));
    });
    card.appendChild(trialLine);
    if (approach.synthetic) {
      card.appendChild(
        make(
          "p",
          null,
          "SYNTHETIC label/content \u2014 metrics appear only when the referenced RunBundle recorded them."
        )
      );
    }
    return card;
  }

  function fillEvalTable(exploration) {
    var tbody = document.getElementById("eval-compare-body");
    clear(tbody);
    exploration.approaches.forEach(function (approach) {
      var row = make("tr");
      var labelCell = make("td");
      labelCell.appendChild(document.createTextNode(approach.label + " "));
      if (approach.synthetic) labelCell.appendChild(syntheticBadge());
      row.appendChild(labelCell);
      var passes = make("td");
      passes.appendChild(
        approach.metrics.passed_trials === null
          ? notRecorded()
          : make("span", null, String(approach.metrics.passed_trials))
      );
      row.appendChild(passes);
      var violations = make("td");
      violations.appendChild(
        approach.metrics.violations === null
          ? notRecorded()
          : make("span", null, String(approach.metrics.violations))
      );
      row.appendChild(violations);
      var tokens = make("td");
      tokens.appendChild(
        approach.metrics.tokens === null ? notRecorded() : make("span", null, String(approach.metrics.tokens))
      );
      row.appendChild(tokens);
      var latency = make("td");
      latency.appendChild(
        approach.metrics.latency_ms === null
          ? notRecorded()
          : make("span", null, approach.metrics.latency_ms + " ms")
      );
      row.appendChild(latency);
      tbody.appendChild(row);
    });
  }

  /* ---------- wiring ---------- */

  function init() {
    if (DATA.title) document.getElementById("studio-title").textContent = DATA.title;
    Array.prototype.slice.call(document.querySelectorAll('[role="tablist"]')).forEach(wireTablist);

    var wsTablist = document.getElementById("workspace-tablist");
    var wsTabIteration = document.getElementById("ws-tab-iteration");
    var wsTabExploration = document.getElementById("ws-tab-exploration");
    if (!DATA.iteration) wsTabIteration.hidden = true;
    if (!DATA.exploration) wsTabExploration.hidden = true;
    if (!DATA.iteration && DATA.exploration) selectTab(wsTablist, wsTabExploration);

    if (DATA.iteration) {
      renderVersionList(DATA.iteration);
      fillVersionSelect(DATA.iteration);
      renderMatrices(DATA.iteration);
      diffIndex = Math.max(diffRange(DATA.iteration), 1);
      updateDiffLabel(DATA.iteration);
    }
    if (DATA.exploration) renderExploration();

    document.querySelector('[data-action="diff-prev"]').addEventListener("click", function () {
      diffIndex = Math.max(diffIndex - 1, 1);
      updateDiffLabel(DATA.iteration);
    });
    document.querySelector('[data-action="diff-next"]').addEventListener("click", function () {
      diffIndex = Math.min(diffIndex + 1, diffRange(DATA.iteration));
      updateDiffLabel(DATA.iteration);
    });
    document.querySelector('[data-action="open-diff"]').addEventListener("click", function (event) {
      renderDiffModal();
      openOverlay(document.getElementById("diff-dialog-wrap"), event.currentTarget);
    });
    document.querySelector('[data-action="diff-modal-prev"]').addEventListener("click", function () {
      diffIndex = Math.max(diffIndex - 1, 1);
      updateDiffLabel(DATA.iteration);
      renderDiffModal();
    });
    document.querySelector('[data-action="diff-modal-next"]').addEventListener("click", function () {
      diffIndex = Math.min(diffIndex + 1, diffRange(DATA.iteration));
      updateDiffLabel(DATA.iteration);
      renderDiffModal();
    });
    document.querySelector('[data-action="close-diff"]').addEventListener("click", function () {
      closeOverlay(document.getElementById("diff-dialog-wrap"));
    });
    document.querySelector('[data-action="trial-prev"]').addEventListener("click", function () {
      if (!drawerState || !dialogState) return;
      dialogState.index = (dialogState.index - 1 + drawerState.trials.length) % drawerState.trials.length;
      renderTrialDialog();
    });
    document.querySelector('[data-action="trial-next"]').addEventListener("click", function () {
      if (!drawerState || !dialogState) return;
      dialogState.index = (dialogState.index + 1) % drawerState.trials.length;
      renderTrialDialog();
    });
    document.querySelector('[data-action="close-dialog"]').addEventListener("click", function () {
      dialogState = null;
      closeOverlay(document.getElementById("trial-dialog-wrap"));
    });
    document.querySelector('[data-action="back-to-list"]').addEventListener("click", function () {
      drawerState = null;
      document.getElementById("trial-drawer").hidden = true;
    });

    document.addEventListener("keydown", function (event) {
      if (event.key !== "Escape") return;
      var diffWrap = document.getElementById("diff-dialog-wrap");
      var trialWrap = document.getElementById("trial-dialog-wrap");
      if (!diffWrap.hidden) {
        closeOverlay(diffWrap);
        return;
      }
      if (!trialWrap.hidden) {
        dialogState = null;
        closeOverlay(trialWrap);
        return;
      }
      var drawer = document.getElementById("trial-drawer");
      if (!drawer.hidden) drawer.hidden = true;
    });
  }

  init();
})();
