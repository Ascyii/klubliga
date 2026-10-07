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
function setupEntryForm(form) {
  const partner = form.querySelector("select[name=partner]");
  const field = partner && partner.closest(".field");
  const preview = form.querySelector("[data-entry-preview]");
  const mySex = form.dataset.mySex;
  const update = () => {
    const kind = form.querySelector("input[name=kind]:checked")?.value || "singles";
    if (field) field.hidden = kind !== "doubles";
    let name = mySex === "M" ? "Men's Singles" : "Women's Singles";
    if (kind === "doubles") {
      const sex = partner.selectedOptions[0]?.dataset.sex;
      if (!sex) name = "";
      else if (sex !== mySex) name = "Mixed Doubles";
      else name = mySex === "M" ? "Men's Doubles" : "Women's Doubles";
    }
    preview.textContent = name ? `Tournament: ${name}` : "";
  };
  form.addEventListener("change", update);
  update();
}
document.querySelectorAll("form[data-entry-form]").forEach(setupEntryForm);

// <score-input>: shows only the sets that are still needed and announces the winner.
class ScoreInput extends HTMLElement {
  connectedCallback() {
    this.bestOf = Number(this.dataset.bestOf) || 3;
    this.toWin = Math.floor(this.bestOf / 2) + 1;
    this.rows = [...this.querySelectorAll(".set-row")];
    this.status = this.querySelector(".score-status");
    this.names = [this.dataset.name1, this.dataset.name2];
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
    this.status.textContent = winner < 0 ? "" :
      `Winner: ${this.names[winner]} (${won[winner]}:${won[1 - winner]} sets)`;
  }
}
customElements.define("score-input", ScoreInput);
