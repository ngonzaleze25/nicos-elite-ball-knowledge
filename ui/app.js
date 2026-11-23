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
refresh();
