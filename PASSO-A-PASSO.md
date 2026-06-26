# PASSO A PASSO — executar a task `optimize-velocity-features` (do zero)

> Siga na ordem, de cima para baixo. Cada bloco tem: **▶ o comando/ação**, **✅ o que esperar**, e **👉 o que fazer**. Se algo divergir, pare e me mande a saída.
>
> Convenções:
> - `[HOST]` = terminal normal do seu computador (fora do container).
> - `[CONTAINER]` = terminal dentro do dev container (depois do passo 1.8).
> - Onde aparecer `<ALGO>` você substitui pelo valor real (sem os sinais `< >`).

---

## PARTE 0 — Você está no Windows com Ubuntu (WSL): leia primeiro

Você roda o terminal Ubuntu via WSL. Tudo funciona, mas preste atenção em 3 coisas.

### 0.1 Confirmar que é WSL **2** (não WSL 1)
▶ Abra o **PowerShell do Windows** (não o Ubuntu) e rode:
```powershell
wsl -l -v
```
✅ Na linha do seu Ubuntu, a coluna **VERSION** tem que ser **2**.
👉 Se for `1`, converta (PowerShell, ajuste o nome se preciso):
```powershell
wsl --set-version Ubuntu 2
```

### 0.2 Docker no WSL = Docker Desktop com integração WSL
▶ Instale o **Docker Desktop for Windows** (https://www.docker.com/products/docker-desktop/).
👉 Abra o Docker Desktop → **Settings**:
- **General** → marque **"Use the WSL 2 based engine"**.
- **Resources → WSL Integration** → **ative o toggle do seu Ubuntu**.
- Clique **Apply & Restart**.
✅ Validar **dentro do terminal Ubuntu (WSL)**:
```bash
docker info
```
✅ Tem que responder com infos do servidor. Se der "Cannot connect", o Docker Desktop não está aberto ou a integração WSL não foi ativada.

### 0.3 ⚠️ ARMADILHA: trabalhe no disco do Linux (`~`), NÃO em `/mnt/c/...`
Se você baixar/extrair o toolkit dentro de `/mnt/c/...` (o disco do Windows), fica **lento** e dá erro de permissão e de quebra de linha (CRLF). **Sempre trabalhe na home do Linux.**
▶ No terminal Ubuntu:
```bash
cd ~
pwd
```
✅ Tem que imprimir `/home/<seu-usuario>` — **não** pode começar com `/mnt/c`.
👉 Se o zip do toolkit está no Downloads do Windows, **mova pra home do Linux** antes de extrair:
```bash
cp /mnt/c/Users/<SeuUsuarioWindows>/Downloads/triton-toolkit-3a9bcb8.zip ~/
cd ~
```

### 0.4 Instalar o Node **dentro** do WSL (não usar o Node do Windows)
▶ No terminal Ubuntu, instale via nvm (não precisa de sudo):
```bash
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
source ~/.nvm/nvm.sh
nvm install --lts
```
✅ Validar:
```bash
node --version
npx --version
```
✅ Ambos imprimem versão.

> Com a Parte 0 feita, pule o "1.1/1.2" abaixo (Docker e Node já estão prontos) e siga do **passo 1.3 (Git)** em diante. Rode **tudo** no terminal Ubuntu (WSL) — nunca no PowerShell, exceto o passo 0.1.

---

## PARTE 1 — Preparar a máquina (uma vez só)

### 1.1 Instalar o Docker Desktop
▶ Baixe e instale: https://www.docker.com/products/docker-desktop/
👉 Abra o Docker Desktop e deixe **rodando**. Em Settings → Resources, garanta **≥ 4 GB de memória**.
✅ Validar `[HOST]`:
```bash
docker info
```
✅ Tem que imprimir informações do servidor (não pode dar "Cannot connect"). Se der erro, o Docker não está rodando — abra o app e espere ele subir.

> **Windows:** instale o **WSL 2** (https://learn.microsoft.com/windows/wsl/install), habilite "WSL 2 backend" no Docker Desktop, e rode TODOS os comandos `[HOST]` dentro de um terminal **WSL (Ubuntu)**, não no PowerShell.

### 1.2 Instalar o Node.js LTS
▶ Baixe e instale a versão **LTS**: https://nodejs.org/
✅ Validar `[HOST]`:
```bash
node --version
npx --version
```
✅ Ambos imprimem um número de versão.

### 1.3 Instalar o Git (se ainda não tiver)
✅ Validar `[HOST]`:
```bash
git --version
```
✅ Imprime a versão. Se não tiver: macOS `xcode-select --install`; Ubuntu/WSL `sudo apt-get update && sudo apt-get install -y git`.

---

## PARTE 2 — Baixar o toolkit e configurar a chave

### 2.1 Baixar e extrair o toolkit
👉 Na plataforma DataAnnotation, na página **Setup**, clique no link **"Download latest toolkit (#3a9bcb8)"** e salve o zip.
▶ `[HOST]` — vá para a pasta onde está o zip e extraia (ajuste o nome do arquivo se preciso). **No WSL** você já moveu o zip para `~` (Parte 0.3):
```bash
cd ~
unzip triton-toolkit-3a9bcb8.zip -d triton-toolkit
cd triton-toolkit
```
> No macOS/Linux nativo, troque `cd ~` por `cd ~/Downloads`.
✅ Validar que você está na raiz do toolkit:
```bash
ls
```
✅ Tem que aparecer, entre outros: `scripts`, `scaffold`, `refs`, `docs`, `CLAUDE.md`.
👉 **A partir daqui, todo comando `[HOST]` é rodado desta pasta (a raiz do toolkit).**

### 2.2 Criar o arquivo `.env` (com a SUA chave)
👉 Na plataforma, na página **Setup**, há um bloco com **4 linhas** (`ANTHROPIC_API_KEY`, `ANTHROPIC_BASE_URL`, `CLAUDE_CODE_MAX_OUTPUT_TOKENS`, `USER_ID`). Você vai copiar **essas 4 linhas exatas**.
▶ `[HOST]` na raiz do toolkit, crie o `.env`:
```bash
cat > .env << 'FIM'
ANTHROPIC_API_KEY=<COLE_AQUI_SUA_CHAVE_DA_PLATAFORMA>
ANTHROPIC_BASE_URL=<COLE_AQUI_A_BASE_URL_DA_PLATAFORMA>
CLAUDE_CODE_MAX_OUTPUT_TOKENS=64000
USER_ID=<COLE_AQUI_SEU_USER_ID_DA_PLATAFORMA>
FIM
```
👉 Abra o `.env` num editor e troque os três `<...>` pelos valores reais da plataforma. **Nunca compartilhe essa chave** (nem no Slack, nem em commit).
✅ Validar (sem expor a chave inteira):
```bash
grep -c ANTHROPIC_API_KEY .env
```
✅ Tem que imprimir `1`.

---

## PARTE 3 — Subir o dev container

### 3.1 Construir e iniciar
▶ `[HOST]` na raiz do toolkit:
```bash
npx @devcontainers/cli up
```
✅ Na **1ª vez** demora alguns minutos (faz build da imagem). Termina com uma linha tipo `{"outcome":"success", ...}`.
👉 Se travar/falhar por rede ou Docker, confirme que o Docker Desktop está aberto e rode de novo.

### 3.2 Entrar no container
▶ `[HOST]`:
```bash
npx @devcontainers/cli exec bash
```
✅ O prompt do terminal muda (você agora está **dentro** do container). **Daqui em diante os comandos marcados `[CONTAINER]` rodam aqui.**

### 3.3 Confirmar que está no container certo
▶ `[CONTAINER]`:
```bash
harbor --version
```
✅ Imprime a versão do `harbor`. Se der "command not found", você **não** está no container — refaça o 3.2.

---

## PARTE 4 — Trazer a task pronta para o toolkit

> A task já está construída e testada no seu repositório Git (branch `claude/data-annotation-task-debug-awxoih`). Vamos copiar a pasta dela para dentro de `tasks/` do toolkit.

### 4.1 Clonar o repositório e copiar a pasta da task
▶ `[CONTAINER]`, a partir da raiz do toolkit (você já está nela):
```bash
git clone -b claude/data-annotation-task-debug-awxoih https://github.com/paulojoseph/triton-da.git /tmp/triton-da
mkdir -p tasks
cp -r /tmp/triton-da/tasks/optimize-velocity-features tasks/
```
👉 Se o `git clone` pedir login, use seu usuário/token do GitHub. Se preferir, faça o clone no `[HOST]` e copie a pasta — o resultado é o mesmo, contanto que `tasks/optimize-velocity-features` exista na raiz do toolkit.

### 4.2 Conferir que os 5 arquivos chegaram
▶ `[CONTAINER]`:
```bash
ls -R tasks/optimize-velocity-features
```
✅ Tem que listar:
```
instruction.md   task.toml
environment/Dockerfile   environment/engine.py   environment/data/transactions.jsonl
solution/solve.sh   solution/solve.py
tests/test.sh   tests/test_outputs.py
```

---

## PARTE 5 — (Opcional, recomendado) Abrir o Claude Code

> Útil pra interpretar saídas dos scripts. Não é obrigatório pra rodar os scripts.

▶ `[CONTAINER]`:
```bash
claude
```
✅ Ele pergunta se quer autenticar pela API key do ambiente → responda **yes** (Enter).
✅ Aparece um aviso de **"Bypass Permissions"** → **aceite** (é esperado e seguro no container).
✅ Pode aparecer "Auth conflict: Using ANTHROPIC_API_KEY…" → **é esperado** (o proxy está roteando certo).
👉 Dentro do Claude Code, digite:
```
/model claude-opus-4-8
/effort max
```
👉 Para sair do Claude Code e voltar ao terminal: tecle `Ctrl+C` duas vezes (ou digite `/exit`).

---

## PARTE 6 — Rodar as fases do toolkit (na ordem)

> Todos `[CONTAINER]`, da raiz do toolkit. **Não precisa editar nenhum arquivo da task** — ela já está pronta e verificada. Você só executa e lê a saída.

### 6.1 Fase Propose — revisão da proposta
▶
```bash
scripts/check-proposal.sh tasks/optimize-velocity-features
```
✅ Gera `tasks/optimize-velocity-features/.proposal-review.md` e imprime, no fim, uma linha **`Decision:`**.
👉 Objetivo: `Decision: Accept` (ou `Strong Accept`). Copie a saída e me mande. Se vier `Uncertain`/`Reject`, **não mexa em nada ainda** — me mande o texto e eu ajusto.

### 6.2 Fase Implement — validação automática
▶
```bash
scripts/validate.sh tasks/optimize-velocity-features
```
✅ Roda static checks + o oráculo (tem que **passar**) + um no-op (tem que **falhar**). No fim deve indicar sucesso geral.
👉 Se falhar, me mande a saída inteira.

### 6.3 Fase Implement — rubrica de qualidade
▶
```bash
scripts/check-quality.sh tasks/optimize-velocity-features
```
✅ Gera `tasks/optimize-velocity-features/.rubric-review.md` com PASS/FAIL por critério (25 no total).
👉 Me mande esse arquivo (ou a contagem final). Mira: tudo PASS.

### 6.4 Fase Trial — o teste de dificuldade (o mais importante)
▶
```bash
scripts/trial.sh tasks/optimize-velocity-features
```
✅ Roda agentes reais contra a task (demora). Gera `job-summary.md` e `trial-analysis.md`.
👉 O que queremos: agentes **falhando** por `difficulty_crux` (não otimizaram dentro do orçamento, ou quebraram uma das 4 sutilezas), **sem** `task_specification: FAIL`, e taxa de aprovação **< 80%**. Me mande o `job-summary.md`.

### 6.5 Fase Trial — cheat trial (anti-atalho)
▶
```bash
scripts/cheat-trial.sh tasks/optimize-velocity-features
```
✅ Roda de novo com um prompt hostil tentando burlar.
👉 Queremos **nenhum** `reward_hacking: FAIL`. Me mande o resumo.

### 6.6 Fase Submit — gerar o tarball
▶ (só depois de tudo acima verde)
```bash
scripts/submit.sh tasks/optimize-velocity-features
```
✅ Gera o pacote final (tarball) para upload.
👉 Faça o **upload do tarball** no campo de submissão da plataforma.

---

## PARTE 7 — Preencher os campos da plataforma (Fase Propose)

| Campo na plataforma | O que selecionar/colar |
|---|---|
| **Category** | `Software engineering` |
| **Task slug** | `optimize-velocity-features` |
| **"What must the agent accomplish, and why is it hard?"** | o parágrafo abaixo |
| **"What decision did check-proposal give?"** | o que apareceu na linha `Decision:` do passo 6.1 |
| **Upload `.proposal-review.md`** | `tasks/optimize-velocity-features/.proposal-review.md` |

**Texto para a caixa "what must the agent accomplish":**

> O agente herda um job de scoring antifraude que calcula "features de velocidade" por transação (quantas transações anteriores da mesma conta caem numa janela de 1h, a soma dos valores, e quantas tiveram valor ≥ o atual) com uma varredura quadrática de todos-os-pares, e por isso estoura o SLA noturno num dia cheio de tráfego. Ele precisa reescrever o job para produzir a saída idêntica, mas terminar em bem menos de um minuto — o que força uma janela deslizante por conta mais uma estrutura de estatística de ordem (um Fenwick/BIT sobre os valores) para a feature "≥": só agrupar e revarrer ainda estoura o orçamento. É difícil porque o ganho exige o insight de estrutura de dados certo preservando semânticas sutis: fronteira de janela inclusiva, empates de timestamp, exclusão do próprio registro e a comparação `≥`.

---

## Atalho de problemas comuns
- `harbor: command not found` → você não está no container. Rode `npx @devcontainers/cli exec bash` (passo 3.2).
- `docker: command not found` / "Cannot connect" → Docker Desktop não está aberto/rodando.
- `ANTHROPIC_API_KEY not set` → o `.env` está faltando/errado (passo 2.2). Saia e re-entre no container.
- "Auth conflict: Using ANTHROPIC_API_KEY…" → **é esperado**, pode ignorar.
- Trial travado em "starting environment" → reinicie o Docker, rode 1 trial primeiro, e confira `harbor-jobs/.../trial.log`.

> A cada passo de 6.1 a 6.5, me cole a saída. Eu te digo se está verde ou se precisa de ajuste — e faço o ajuste na task na hora.
