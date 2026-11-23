"use strict";

const config = window.BETLEDGER_CONFIG;
const byId = (id) => document.getElementById(id);
const euros = new Intl.NumberFormat("en-IE", { style: "currency", currency: "EUR" });
const kickoffFormat = new Intl.DateTimeFormat("en-GB", {
    day: "numeric", month: "short", year: "numeric",
    hour: "2-digit", minute: "2-digit",
});
const fixtureStates = {
    SCHEDULED: "Scheduled",
    TIMED: "Confirmed",
    IN_PLAY: "In play",
    PAUSED: "Half time",
    EXTRA_TIME: "Extra time",
    PENALTY_SHOOTOUT: "Penalties",
    FINISHED: "Finished",
    SUSPENDED: "Suspended",
    POSTPONED: "Postponed",
    CANCELLED: "Cancelled",
    AWARDED: "Awarded",
};
const unconfirmedKickoff = new Set(["SCHEDULED", "POSTPONED", "CANCELLED"]);
let fixtures = null;

function message(element, text, state = "") {
    element.textContent = text;
    element.dataset.state = state;
}

async function requestJson(baseUrl, path, body, timeoutMs = 12000) {
    if (!baseUrl) throw new Error("The API address is missing. Check config.js.");
    const options = { signal: AbortSignal.timeout(timeoutMs) };
    if (body) {
        options.method = "POST";
        options.headers = { "Content-Type": "application/json" };
        options.body = JSON.stringify(body);
    }
    let response;
    try {
        response = await fetch(baseUrl.replace(/\/+$/, "") + path, options);
    } catch {
        throw new Error(body
            ? "Could not confirm the save. Refresh before trying again."
            : "The service could not be reached. Try Refresh.");
    }
    const data = await response.json().catch(() => null);
    if (response.status === 503 && !data?.error) {
        throw new Error("The service may be starting up. Try again shortly.");
    }
    if (!response.ok) {
        throw new Error(data?.error || "The request failed (HTTP " + response.status + ").");
    }
    if (!data) throw new Error("The service returned an unreadable response.");
    return data;
}

async function loadBalance() {
    const balance = byId("balance");
    try {
        const data = await requestJson(config?.bankrollUrl, "/balance");
        message(balance, euros.format(data.balance_cents / 100));
    } catch (error) {
        message(balance, error.message, "error");
    }
}

function renderFixtures() {
    if (fixtures === null) return;
    const status = byId("fixture-status");
    const table = byId("fixture-table");
    const upcoming = byId("fixture-filter").value === "upcoming";
    const visible = upcoming ? fixtures.filter((match) => (
        match.source_status === "SCHEDULED" || match.source_status === "TIMED"
    )) : fixtures;
    const rows = visible.map((match) => {
        const row = document.createElement("tr");
        const kickoff = new Date(match.kickoff_at);
        const hasTime = match.kickoff_at && !unconfirmedKickoff.has(match.source_status)
            && !Number.isNaN(kickoff.getTime());
        const label = fixtureStates[match.source_status];
        const score = match.home_goals !== null && match.away_goals !== null
            ? " · " + match.home_goals + "–" + match.away_goals : "";
        for (const text of [
            match.home_team + " vs " + match.away_team,
            hasTime ? kickoffFormat.format(kickoff) : "Kickoff TBC",
            label + score,
        ]) {
            const cell = document.createElement("td");
            cell.textContent = text;
            row.append(cell);
        }
        return row;
    });
    byId("fixtures").replaceChildren(...rows);
    table.hidden = rows.length === 0;
    const emptyMessage = fixtures.length === 0
        ? "No fixtures yet. Select Sync LaLiga fixtures to load the schedule."
        : "No upcoming fixtures.";
    message(status, rows.length === 0 ? emptyMessage : "");
}

async function loadFixtures() {
    const journalBalance = byId("journal-balance");
    try {
        const data = await requestJson(config?.journalUrl, "/matches");
        fixtures = data.matches;
        renderFixtures();
        renderBettingFixtures();
        message(journalBalance, data.bankroll_status === "ok"
            ? "Balance reported to Journal: " + euros.format(data.balance_cents / 100)
            : "Bankroll is unavailable. Journal fixtures are still available.");
    } catch (error) {
        fixtures = null;
        byId("fixture-table").hidden = true;
        message(journalBalance, "");
        message(byId("fixture-status"), error.message, "error");
    }
}

async function refresh() {
    const button = byId("refresh");
    button.disabled = true;
    try {
        await Promise.all([loadBalance(), loadFixtures()]);
    } finally {
        button.disabled = false;
    }
}

function depositPayload(fields) {
    const match = fields.get("amount").trim().match(/^(\d{1,8})(?:[.,](\d{1,2}))?$/);
    const cents = match ? Number(match[1]) * 100 + Number((match[2] || "").padEnd(2, "0")) : 0;
    if (cents < 1 || cents > 2147483647) {
        throw new Error("Enter a positive euro amount with up to two decimal places.");
    }
    return { amount_cents: cents, description: fields.get("description").trim() };
}

function bindForm(formId, messageId, baseUrl, path, payload, successMessage, timeoutMs) {
    const form = byId(formId);
    const output = byId(messageId);
    const button = form.querySelector("button");
    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        button.disabled = true;
        message(output, "Saving…");
        try {
            await requestJson(baseUrl, path, payload(new FormData(form)), timeoutMs);
            form.reset();
            message(output, successMessage, "success");
            await refresh();
        } catch (error) {
            message(output, error.message, "error");
        } finally {
            button.disabled = false;
        }
    });
}

const kellyForm = byId("kelly-form");
kellyForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = kellyForm.querySelector("button");
    const output = byId("kelly-result");
    const fields = new FormData(kellyForm);
    button.disabled = true;
    message(output, "Calculating…");

    try {
        const data = await requestJson(config?.bankrollUrl, "/kelly", {
            decimal_odds: Number(fields.get("odds")),
            probability: Number(fields.get("probability")) / 100,
        });
        const suggested = euros.format(data.suggested_stake_cents / 100);
        const full = euros.format(data.full_kelly_cents / 100);
        message(output, `Suggested stake: ${suggested} (full Kelly: ${full}).`, "success");
    } catch (error) {
        const text = error.message === "Could not confirm the save. Refresh before trying again."
            ? "The calculator could not reach Bankroll. Try again shortly."
            : error.message;
        message(output, text, "error");
    } finally {
        button.disabled = false;
    }
});

bindForm("deposit-form", "deposit-message", config?.bankrollUrl, "/deposits", depositPayload, "Deposit recorded.");
bindForm("fixture-form", "fixture-message", config?.journalUrl, "/matches/sync", () => ({}), "Fixtures synced.", 25000);
byId("fixture-filter").addEventListener("change", renderFixtures);
byId("refresh").addEventListener("click", refresh);
const bettingFixture = byId("betting-fixture");
const bettingMessage = byId("betting-message");
const bettingDetail = byId("betting-detail");
const percent = new Intl.NumberFormat("en-IE", { style: "percent", maximumFractionDigits: 2 });

function renderBettingFixtures() {
    const selected = bettingFixture.value;
    const options = fixtures.map((fixture) => {
        const option = document.createElement("option");
        option.value = fixture.id;
        const kickoff = fixture.kickoff_at && !unconfirmedKickoff.has(fixture.source_status)
            ? " · " + kickoffFormat.format(new Date(fixture.kickoff_at)) : "";
        option.textContent = fixture.home_team + " vs " + fixture.away_team + kickoff;
        return option;
    });
    bettingFixture.replaceChildren(new Option("Choose a fixture", ""), ...options);
    bettingFixture.value = options.some((option) => option.value === selected) ? selected : "";
    bettingFixture.disabled = options.length === 0;
    bettingDetail.hidden = !bettingFixture.value;
}

function actionButton(text, action) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = text;
    button.addEventListener("click", () => performBettingAction(button, action));
    return button;
}

async function performBettingAction(button, action) {
    const fixture = bettingFixture.value;
    button.disabled = true;
    message(bettingMessage, "Working…");
    try {
        const confirmation = await action(fixture);
        await refresh();
        if (bettingFixture.value === fixture) {
            await loadBettingDetail();
            if (!bettingDetail.hidden) message(bettingMessage, confirmation, "success");
        }
    } catch (error) {
        if (bettingFixture.value === fixture) message(bettingMessage, error.message, "error");
    } finally {
        button.disabled = false;
    }
}

function showDecision(decision, bet, bankrollAvailable) {
    const row = document.createElement("li");
    const detail = document.createElement("p");
    const implied = 1 / Number(decision.decimal_odds);
    const margin = decision.model_probability - implied;
    detail.textContent = `${decision.bookmaker} · ${decision.selection} at ${decision.decimal_odds} · Estimate ${percent.format(decision.model_probability)} · Implied ${percent.format(implied)} · ${margin > 0 ? "Possible value" : "No value"}`;
    row.append(detail);
    const quote = document.createElement("button");
    quote.type = "button";
    quote.textContent = "Calculate Kelly";
    quote.addEventListener("click", () => {
        byId("kelly-odds").value = decision.decimal_odds;
        byId("kelly-probability").value = decision.model_probability * 100;
        kellyForm.scrollIntoView({ block: "center" });
        kellyForm.requestSubmit();
    });
    row.append(quote);
    if (!bankrollAvailable) return row;

    if (!bet) {
        const form = document.createElement("form");
        const label = document.createElement("label");
        const input = document.createElement("input");
        input.type = "number";
        input.min = "0.01";
        input.max = "10";
        input.step = "0.01";
        input.required = true;
        label.textContent = "Stake (€)";
        label.append(input);
        const submit = document.createElement("button");
        submit.textContent = "Record bet";
        form.append(label, submit);
        form.addEventListener("submit", (event) => {
            event.preventDefault();
            performBettingAction(submit, async () => {
                await requestJson(config?.bankrollUrl, "/bets", {
                    decision_id: decision.id,
                    stake_cents: Math.round(Number(input.value) * 100),
                });
                return "Bet recorded.";
            });
        });
        row.append(form);
        return row;
    }

    const state = document.createElement("p");
    state.textContent = `${euros.format(bet.stake_cents / 100)} · ${bet.status}`;
    row.append(state);
    if (bet.status === "open") {
        for (const [text, isVoid] of [["Settle from final score", false], ["Void bet", true]]) {
            row.append(actionButton(text, async () => {
                const result = await requestJson(config?.bankrollUrl, `/bets/${bet.id}/settlement`, { void: isVoid });
                return `Bet settled as ${result.status}.`;
            }));
        }
    }
    return row;
}

let bettingRequest = 0;
async function loadBettingDetail() {
    const requestId = ++bettingRequest;
    const fixture = bettingFixture.value;
    bettingDetail.hidden = true;
    message(bettingMessage, fixture ? "Loading fixture details…" : "");
    if (!fixture) return;
    try {
        const [data, bankroll] = await Promise.all([
            requestJson(config?.journalUrl, `/matches/${fixture}/betting`),
            requestJson(config?.bankrollUrl, "/bets").catch(() => null),
        ]);
        if (requestId !== bettingRequest || bettingFixture.value !== fixture) return;

        const probabilities = data.estimate?.probabilities;
        message(byId("betting-estimate"), probabilities
            ? Object.entries(probabilities).map(([outcome, probability]) =>
                `${outcome}: ${percent.format(probability)}`).join(" · ")
            : data.estimate_message);
        const odds = data.odds.map((item) => {
            const row = document.createElement("li");
            row.textContent = `${item.bookmaker} · Home ${item.home_odds} · Draw ${item.draw_odds} · Away ${item.away_odds}`;
            return row;
        });
        byId("betting-odds").replaceChildren(...odds);
        const betsByDecision = new Map((bankroll?.bets || []).map((bet) => [bet.decision_id, bet]));
        byId("betting-decisions").replaceChildren(...data.decisions.map((decision) =>
            showDecision(decision, betsByDecision.get(decision.id), Boolean(bankroll))));
        message(byId("bets-status"), bankroll ? "" : "Bankroll is unavailable. Saved odds and decisions are still visible.");
        bettingDetail.hidden = false;
        message(bettingMessage, "");
    } catch (error) {
        if (requestId === bettingRequest) message(bettingMessage, error.message, "error");
    }
}

bettingFixture.addEventListener("change", loadBettingDetail);
for (const [formId, endpoint, confirmation] of [
    ["odds-form", "odds", "Bookmaker odds saved."],
    ["decision-form", "decisions", "Decision saved."],
]) {
    const form = byId(formId);
    form.addEventListener("submit", (event) => {
        event.preventDefault();
        const fields = Object.fromEntries(new FormData(form));
        for (const name of ["home_odds", "draw_odds", "away_odds"]) {
            if (name in fields) fields[name] = Number(fields[name]);
        }
        performBettingAction(form.querySelector("button"), async (fixture) => {
            await requestJson(config?.journalUrl, `/matches/${fixture}/${endpoint}`, fields);
            return confirmation;
        });
    });
}

refresh();
