# Klockan

GitHub startade 14 av 58 schemalagda körningar mellan 25 och 27 oktober, med upp till två timmars försening.
Klockan är en Cloudflare Worker som startar workflows direkt med `workflow_dispatch`:

- `pipeline.yml` varje timme (kvart över, ungefär)
- `instagram.yml` kl 07.45 svensk tid

GitHubs egna scheman ligger kvar som reserv. Workflowerna har en gemensam concurrency-grupp, så två starter
nära varandra köas i stället för att krocka.

## Sätt upp den (fem minuter, i webbläsaren)

1. Skapa en token på GitHub: Settings, Developer settings, Fine-grained tokens, Generate new token.
   Bara repot `newsnavigator-pipeline`, behörighet **Actions: Read and write**, inget annat. Giltig i ett år.
2. I Cloudflare: Workers & Pages, Create, Create Worker. Namnge den `newsnavigator-klocka`, Deploy.
3. Edit code: ersätt koden med innehållet i `worker.js`, Deploy.
4. Settings, Variables and Secrets, Add: typ **Secret**, namn `GITHUB_TOKEN`, värdet är din token.
5. Settings, Trigger events, Add, Cron trigger: `2,17,32,47 * * * *`.
6. Öppna Workerns adress i webbläsaren. Den visar svensk tid, vad som skulle startas nu och `"token": true`.

Med wrangler i stället: `cd klocka && npx wrangler deploy && npx wrangler secret put GITHUB_TOKEN`.

Kontroll: `data/drift.json` visar varje körning. Efter ett dygn ska pipelinen ha gått varje timme.
