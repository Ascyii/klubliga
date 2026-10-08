// Klubliga – progressive enhancements. Every page works without this file.

// Ask for confirmation before submitting dangerous actions.
document.addEventListener("click", (event) => {
  const el = event.target.closest("[data-confirm]");
  if (el && !window.confirm(el.dataset.confirm)) event.preventDefault();
});

// Submit filter forms as soon as a value changes.
document.addEventListener("change", (event) => {
  const form = event.target.closest("form[data-autosubmit]");
  if (form) form.requestSubmit();
});

// New entry form: show the partner field only for doubles and preview the tournament.
// The translated preview texts come from the page (#tournament-previews, keyed by tournament code).
function setupEntryForm(form) {
  const partner = form.querySelector("select[name=partner]");
  const field = partner && partner.closest(".field");
  const preview = form.querySelector("[data-entry-preview]");
  const mySex = form.dataset.mySex;
  const texts = JSON.parse(document.getElementById("tournament-previews")?.textContent || "{}");
  const update = () => {
    const kind = form.querySelector("input[name=kind]:checked")?.value || "singles";
    if (field) field.hidden = kind !== "doubles";
    let code = mySex === "M" ? "MS" : "WS";
    if (kind === "doubles") {
      const sex = partner.selectedOptions[0]?.dataset.sex;
      if (!sex) code = "";
      else if (sex !== mySex) code = "XD";
      else code = mySex === "M" ? "MD" : "WD";
    }
    preview.textContent = texts[code] || "";
  };
  form.addEventListener("change", update);
  update();
}
document.querySelectorAll("form[data-entry-form]").forEach(setupEntryForm);

// <score-input>: shows only the sets that are still needed and announces the winner.
// data-winner-text is the translated announcement with {name} and {sets} placeholders.
class ScoreInput extends HTMLElement {
  connectedCallback() {
    this.bestOf = Number(this.dataset.bestOf) || 3;
    this.toWin = Math.floor(this.bestOf / 2) + 1;
    this.rows = [...this.querySelectorAll(".set-row")];
    this.status = this.querySelector(".score-status");
    this.names = [this.dataset.name1, this.dataset.name2];
    this.winnerText = this.dataset.winnerText || "Winner: {name} ({sets} sets)";
    this.addEventListener("input", () => this.update());
    const form = this.closest("form");
    if (form) form.addEventListener("change", () => this.update());
    this.update();
  }

  update() {
    const outcome = this.closest("form")?.querySelector("input[name=outcome]:checked");
    const played = !outcome || outcome.value === "played";
    this.hidden = !played;
    const won = [0, 0];
    let complete = true;
    this.rows.forEach((row, index) => {
      const inputs = [...row.querySelectorAll("input")];
      const visible = played && (index < this.toWin || (complete && Math.max(...won) < this.toWin));
      row.hidden = !visible;
      inputs.forEach((input) => { input.disabled = !visible; });
      if (!visible) return;
      const [a, b] = inputs.map((input) => input.value === "" ? null : Number(input.value));
      if (a === null || b === null || a === b) {
        complete = false;
        return;
      }
      won[a > b ? 0 : 1] += 1;
    });
    const winner = won[0] >= this.toWin ? 0 : won[1] >= this.toWin ? 1 : -1;
    this.status.textContent = winner < 0 ? "" : this.winnerText
      .replace("{name}", this.names[winner])
      .replace("{sets}", `${won[winner]}:${won[1 - winner]}`);
  }
}
customElements.define("score-input", ScoreInput);
