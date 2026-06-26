# Guia passo a passo — Autoria de uma task Triton (do zero)

Objetivo: produzir **uma** task terminal que seja difícil para agentes de fronteira,
verificável de forma determinística e resistente a atalhos — e submetê-la.

---

## 0. A régua (leia antes de tudo)

Uma boa task Triton é, ao mesmo tempo:
- **Difícil pelo motivo certo** — trabalho real que alguém é pago pra fazer, além da
  fronteira atual; o agente falha por causa do desafio, não por adivinhação.
- **Verificável** — um pytest determinístico decide certo/errado; sem juiz-LLM.
- **Reprodutível** — mesma imagem, mesmo veredito; deps pinadas.
- **Anti-cheat** — não dá pra passar sem fazer o trabalho.

### Os 4 erros fatais (que já cometemos e vamos evitar)
1. **TOO EASY** — a instrução entrega a solução, ou é um "escreva um programa que faz X".
   Teste rápido: *se o Opus escreve o `solve.sh` de primeira, sem idas e vindas, é fácil demais.*
2. **BIVALENT PHRASING** — uma frase com duas leituras razoáveis e o verificador aceita só
   uma. Sintoma no trial: vários agentes falham no MESMO teste pelo MESMO motivo. É o
   **#1 motivo de rejeição**.
3. **VALORES ESPERADOS ERRADOS** — hardcodar números que não batem com o oráculo. Solução:
   o teste calcula a "verdade" por um **método independente** sobre os dados gerados.
4. **INSTRUÇÃO COM CARA DE IA / OVER-SPEC** — descrever procedimento em vez do objetivo,
   texto sistemático demais. A instrução descreve o QUÊ (o estado final), não o COMO.

---

## Fase 0 — Setup (na sua máquina)

```bash
# pré-requisitos: Docker Desktop (≥4GB) rodando, Node LTS
# extrair o toolkit zip, abrir terminal na raiz do toolkit
# criar .env com ANTHROPIC_API_KEY, ANTHROPIC_BASE_URL, CLAUDE_CODE_MAX_OUTPUT_TOKENS=64000, USER_ID
npx @devcontainers/cli up
npx @devcontainers/cli exec bash      # entra no container
claude                                # autentica via API key do ambiente
# dentro do claude:  /model claude-opus-4-8   e   /effort max
```
✅ **Confirme:** `harbor --version` responde e `claude --print "auth-ok"` responde.
⚠️ O effort volta pra `xhigh` ao reabrir — sempre re-setar pra `max`.

---

## Fase 1 — Ideação (escolher O QUE construir) ← começamos aqui

A parte mais difícil. Uma implementação linda de uma ideia ruim é rejeitada.

### Os 3 levers de dificuldade legítima
- **Horizonte longo** — várias sub-metas dependentes; o agente precisa planejar/verificar.
- **Ambiente rico** — múltiplos arquivos/serviços/DBs; um repo meio quebrado pra navegar.
- **Conhecimento expert** — raciocínio de domínio que um generalista não blefa.

### O que a Triton está "faminta" por
- **Velocidade/eficiência** — deixar código existente mensuravelmente mais rápido (benchmark
  vs baseline). Verificação limpa: tempo < limiar **E** saída correta.
- **Complexidade de produção** — logs reais, topologias de serviços, filesystems semeados.
- **Bug report real → teste de regressão** — distilar um bug verdadeiro num teste.
- **Sistemas distribuídos / data engineering** — dedup fuzzy, inferência de schema, reconciliação.

### Anti-padrões (evite)
- "Escreva um programa que faz X" do zero (resolvido).
- Quebra-cabeças de matemática/cálculo.
- ML trivial (treinar MNIST a 90%).
- Dificuldade só model-specific (filtrar prompts que o modelo atual falha).

### Como decidir
1. **Parta do seu domínio mais forte** — o que VOCÊ faz/fez no trabalho. Tasks fortes nascem
   de trabalho real. (Me diga sua área: backend? dados? SRE? segurança? compiladores?)
2. Escreva 2-3 frases: *o que o agente faz e por que é difícil*.
3. Rascunhe um `instruction.md` curto e rode `scripts/check-proposal.sh tasks/<slug>` até `Accept`.

```bash
scripts/new-task.sh <slug>     # slug: kebab-case, ≤5 palavras, <30 chars, descreve o cerne
# escreva tasks/<slug>/instruction.md
scripts/check-proposal.sh tasks/<slug>
```

---

## Fase 2 — Propose (instruction.md)

### Como escrever a instrução
- **Voz humana, 2-4 parágrafos.** Como um chamado de engenheiro, não spec gerada.
- **Objetivo, não procedimento.** Diga o estado final desejado; o agente decide o como.
- **Paths absolutos** sempre (`/app/output.json`).
- **Schema de saída explícito** (chaves, tipos, casas decimais).
- **Cravar os "gotchas"** sem ambiguidade (ex.: arredondamento, percentil, fronteiras `>` vs `≥`).

### Trave o contrato (anti-bivalência)
Antes de implementar, faça uma tabela **requisito ↔ teste**. Cada requisito load-bearing da
instrução tem que ter um teste que o enforça, e vice-versa. Reescritas de "voz" não podem
apagar nenhum requisito.

⚠️ **Auto-checagem:** releia cada "deve/should". Um leitor cuidadoso chega em OUTRA resposta
aceitável? Se sim, comprometa-se a UMA leitura e escreva-a.

---

## Fase 3 — Implement (os 5 arquivos)

Ordem recomendada (a maior parte do tempo é aqui):

1. **`solution/solve.py` (oráculo)** — a solução correta. Escreva primeiro: ela define a
   verdade. Não pode ter saídas hardcodadas.
2. **`tests/test_outputs.py`** — geradores de dados determinísticos + a **"verdade"
   calculada por método independente** (força bruta no próprio teste) + asserts comparando a
   saída do agente com a verdade + medição de RSS. Regenere dados ocultos a cada run e apague
   `output.json` antes (anti-hardcode).
3. **`environment/aggregator.py` (ou pipeline) — o seed quebrado** que o agente herda.
4. **`environment/Dockerfile`** — só o que o agente precisa; **não** copie `tests/` nem
   `solution/`; deps de teste vão no `tests/test.sh`; apt com `update` + `rm -rf lists`, sem pinar apt.
5. **`task.toml`** — `category`, `expert_time_estimate_hours`, recursos.

### 🔑 Regra de ouro: VERIFICAR RODANDO
Antes de seguir, prove empiricamente (rodando, não lendo):
- ✅ Oráculo **passa** todos os testes.
- ✅ Seed quebrado (nop) **falha**.
- ✅ Memória/limiar: a solução ingênua **estoura**; o oráculo fica folgado.
- ✅ **Cada bug/requisito é load-bearing**: injete um defeito de cada vez no oráculo e
  confirme que cada um sozinho reprova. (Sem crédito parcial.)
- ✅ **Determinístico**: gere os dados 2× e confirme verdade idêntica.

```bash
scripts/validate.sh      tasks/<slug>     # oráculo + nop + static checks
scripts/check-quality.sh tasks/<slug>     # rubrica de 25 critérios
```

---

## Fase 4 — Trial & Cheat-trial (calibração de dificuldade)

```bash
scripts/trial.sh        tasks/<slug>      # 5 runs substantivos
scripts/cheat-trial.sh  tasks/<slug>      # prompt hostil prepended
```

Leia o `job-summary.md` / `trial-analysis.md`:
- **Maioria passa → fácil demais.** Aumente dificuldade.
- **`difficulty_crux: PASS`** → o agente falhou pelo desafio certo. É o que você quer.
- **`task_specification: FAIL`** ou **falha convergente no mesmo teste** → defeito de spec
  (bivalência), não dificuldade. Reescreva a frase ambígua.
- **`low_timeout: FAIL`** → suba `[agent] timeout_sec`.
- **Cheat-trial com `reward_hacking: FAIL`** → endureça (regenere dados, compare com verdade
  independente, nunca só "arquivo existe").

⚠️ Pass rate ≥ 80% **bloqueia** a submissão. Mire em agentes falhando pelo motivo certo.

---

## Fase 5 — Submit

```bash
scripts/submit.sh tasks/<slug>            # gera o tarball pra upload
```

### Checklist final antes do submit
- [ ] `check-proposal` = Accept/Strong Accept
- [ ] `validate` verde (oráculo passa, nop falha)
- [ ] `check-quality` = 25 PASS (ou desvios justificados)
- [ ] `trial` falhando pelo `difficulty_crux`, sem `task_specification: FAIL`
- [ ] `cheat-trial` sem `reward_hacking`
- [ ] `instruction.md` em voz humana, paths absolutos, schema explícito
- [ ] Cada requisito load-bearing tem teste; cada teste rastreia a um requisito
```
