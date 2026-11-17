const byId = (id) => document.getElementById(id);
const actions = {retrieve: "Retrieve and return", read_nfc: "Read NFC message", return_to_start: "Return to start", stop: "Stop mission"};
let currentMission = null;
let proposedMission = null;

function describe(mission) {
  const target = mission.target ? `${mission.target.color} ${mission.target.object_type}` : "No target";
  return `${actions[mission.action]} · ${target}`;
}

function clearResult() {
  proposedMission = null;
  byId("mission-summary").hidden = true;
  byId("use-context").hidden = true;
  byId("json-details").hidden = true;
  byId("json-details").open = false;
  byId("json").textContent = "";
}

document.querySelectorAll("[data-example]").forEach((button) => {
  button.addEventListener("click", () => {
    byId("intent").value = button.dataset.example;
    byId("intent").focus();
  });
});

byId("clear-context").addEventListener("click", () => {
  currentMission = null;
  byId("context-text").textContent = "No previous mission selected.";
  byId("clear-context").hidden = true;
  byId("intent").focus();
});

byId("use-context").addEventListener("click", () => {
  currentMission = proposedMission;
  byId("context-text").textContent = describe(currentMission);
  byId("clear-context").hidden = false;
  byId("intent").value = "";
  byId("intent").focus();
});

byId("intent-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const text = byId("intent").value.trim();
  if (!text) {
    byId("intent").setCustomValidity("Enter a mission objective.");
    byId("intent").reportValidity();
    return;
  }
  clearResult();
  byId("inputs").disabled = true;
  byId("intent-form").setAttribute("aria-busy", "true");
  byId("status").dataset.state = "loading";
  byId("status").textContent = "Interpreting…";
  byId("message").textContent = "Waiting for the local model. The first request may take longer while it loads.";
  try {
    const response = await fetch("/api/interpret", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({text, current_mission: currentMission}),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error?.message || "The request could not be completed.");
    const {status, mission, message} = result.interpretation;
    byId("status").dataset.state = status;
    byId("status").textContent = {ready: "Proposal ready", clarification_required: "Clarification needed", rejected: "Unsupported request"}[status];
    byId("message").textContent = message;
    byId("json").textContent = JSON.stringify(result, null, 2);
    byId("json-details").hidden = false;
    if (status === "ready") {
      proposedMission = mission;
      byId("action").textContent = actions[mission.action];
      byId("target").textContent = mission.target ? `${mission.target.color} ${mission.target.object_type}` : "No target";
      byId("mission-summary").hidden = false;
      byId("use-context").hidden = false;
    }
  } catch (error) {
    byId("status").dataset.state = "error";
    byId("status").textContent = "Interpretation unavailable";
    byId("message").textContent = error.message;
  } finally {
    byId("inputs").disabled = false;
    byId("intent-form").setAttribute("aria-busy", "false");
  }
});

byId("intent").addEventListener("input", () => byId("intent").setCustomValidity(""));
