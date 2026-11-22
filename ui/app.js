"use strict";

const config = window.BETLEDGER_CONFIG;
const byId = (id) => document.getElementById(id);
const euros = new Intl.NumberFormat("en-IE", { style: "currency", currency: "EUR" });
const kickoffFormat = new Intl.DateTimeFormat("en-GB", {
    day: "numeric", month: "short", year: "numeric",
    hour: "2-digit", minute: "2-digit", timeZoneName: "short",
});

function message(element, text, state = "") {
    element.textContent = text;
    element.dataset.state = state;
}

async function requestJson(baseUrl, path, body) {
    if (!baseUrl) throw new Error("The API address is missing. Check config.js.");
    const options = { signal: AbortSignal.timeout(12000) };
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
    if (response.status === 503) {
        throw new Error("The service may be starting up. Try again shortly.");
    }
    const data = await response.json().catch(() => null);
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

async function loadFixtures() {
    const status = byId("fixture-status");
    const table = byId("fixture-table");
    const journalBalance = byId("journal-balance");
    try {
        const data = await requestJson(config?.journalUrl, "/matches");
        const rows = data.matches.map((match) => {
            const row = document.createElement("tr");
            const kickoff = new Date(match.kickoff_at);
            const cells = [
                match.home_team + " vs " + match.away_team,
                Number.isNaN(kickoff.getTime()) ? match.kickoff_at : kickoffFormat.format(kickoff),
                match.status === "finished"
                    ? "Finished · " + match.home_goals + "–" + match.away_goals
                    : "Scheduled",
            ];
            for (const text of cells) {
                const cell = document.createElement("td");
                cell.textContent = text;
                row.append(cell);
            }
            return row;
        });
        byId("fixtures").replaceChildren(...rows);
        table.hidden = rows.length === 0;
        message(status, rows.length === 0 ? "No fixtures yet." : "");
        message(journalBalance, data.bankroll_status === "ok"
            ? "Balance reported to Journal: " + euros.format(data.balance_cents / 100)
            : "Bankroll is unavailable. Journal fixtures are still available.");
    } catch (error) {
        table.hidden = true;
        message(journalBalance, "");
        message(status, error.message, "error");
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

function fixturePayload(fields) {
    const kickoff = new Date(fields.get("kickoff_at"));
    if (Number.isNaN(kickoff.getTime())) throw new Error("Enter a valid kickoff time.");
    return {
        home_team: fields.get("home_team").trim(),
        away_team: fields.get("away_team").trim(),
        kickoff_at: kickoff.toISOString(),
    };
}

function bindForm(formId, messageId, baseUrl, path, payload, successMessage) {
    const form = byId(formId);
    const output = byId(messageId);
    const button = form.querySelector("button");
    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        button.disabled = true;
        message(output, "Saving…");
        try {
            await requestJson(baseUrl, path, payload(new FormData(form)));
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

bindForm("deposit-form", "deposit-message", config?.bankrollUrl, "/deposits", depositPayload, "Deposit recorded.");
bindForm("fixture-form", "fixture-message", config?.journalUrl, "/matches", fixturePayload, "Fixture added.");
byId("refresh").addEventListener("click", refresh);
refresh();
