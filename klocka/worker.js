// Newsnavigators klocka: en Cloudflare Worker som startar GitHub-workflows i tid.
// GitHubs egna scheman hoppar över eller försenar körningar på konton med lite trafik,
// så Workern startar dem med workflow_dispatch, som GitHub kör direkt. Schemana i
// workflowerna finns kvar som reserv. Secret: GITHUB_TOKEN (fine-grained, bara detta repo,
// Actions: läs och skriv).

const REPO = "fabsaku/newsnavigator-pipeline";

// Lokal tid i Stockholm, så att 07.45 är 07.45 både sommar- och vintertid.
function stockholm(date) {
  const parts = new Intl.DateTimeFormat("sv-SE", {
    timeZone: "Europe/Stockholm", hour: "2-digit", minute: "2-digit", hour12: false,
  }).formatToParts(date);
  const get = (t) => Number(parts.find((p) => p.type === t).value);
  return { hour: get("hour"), minute: get("minute") };
}

// Vad som ska startas vid en viss lokal tid. Workern körs var femtonde minut.
function due(t) {
  const jobs = [];
  if (t.minute < 15) jobs.push("pipeline.yml");                   // varje timme
  if (t.minute >= 30 && t.minute < 45) jobs.push("rapport.yml");   // vakthund varje timme: varningsmejl
  if (t.hour === 7 && t.minute < 15) jobs.push("rapport.yml");     // morgonrapporten 07.00
  if (t.hour === 7 && t.minute >= 45) jobs.push("instagram.yml");  // 07.45
  return jobs;
}

async function dispatch(env, workflow) {
  const r = await fetch(`https://api.github.com/repos/${REPO}/actions/workflows/${workflow}/dispatches`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.GITHUB_TOKEN}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "newsnavigator-klocka",
    },
    body: JSON.stringify({ ref: "main" }),
  });
  return `${workflow}: ${r.status}${r.ok ? "" : " " + (await r.text()).slice(0, 200)}`;
}

export default {
  async scheduled(event, env, ctx) {
    const jobs = due(stockholm(new Date(event.scheduledTime)));
    const results = await Promise.all(jobs.map((w) => dispatch(env, w)));
    console.log(results.join(" | ") || "inget att starta");
  },
  // GET visar vad som skulle startas just nu, utan att starta något.
  async fetch(request, env) {
    const t = stockholm(new Date());
    return new Response(JSON.stringify({ stockholm: t, skulle_starta: due(t), token: Boolean(env.GITHUB_TOKEN) }, null, 1),
      { headers: { "content-type": "application/json; charset=utf-8" } });
  },
};
