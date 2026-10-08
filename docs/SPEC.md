# SPEC: nfse-poc

Rascunho gerado no Bootstrap (T-000) em 2026-10-07. Marcações:

- sem marca: observado no repositório ou executado nesta data;
- `[HUMAN]`: informado pelo humano na conversa de 2026-10-07, não confirmável pelo repositório;
- `[INFERRED]`: deduzido por mim, não observado diretamente;
- `[VERIFY: …]`: ainda não checado; nenhum código pode depender disso antes da checagem.

## §0 Rules for agents

Approved: 2026-10-07

(Aprovação dada pelo humano na conversa de 2026-10-07 e transcrita aqui pelo agente. A aprovação cobre o spec; os invariants candidatos de §4 estavam pendentes em Q-01 e foram aprovados depois, ver DEC-004.)

- Quem aprova: Paulo Reis (único autor em `git log`) aprova o spec, os invariants e os phase gates, e decide quando uma task está `done`.
- Regras específicas do projeto, além do `CLAUDE.md`: os invariants de §4 e as três abaixo.
- `Approved` e `done` (DEC-007): o agente só escreve essas marcas quando o humano pedir explicitamente na conversa, e anota a data e que foi transcrição. O agente nunca deduz uma aprovação.
- Idioma (DEC-006): em inglês os termos do `CLAUDE.md` (gate, invariant, milestone, task, frozen, boundary, claim, acceptance criteria, open question), os títulos de seção e de coluna deste spec, as mensagens de commit, os títulos e textos de PR e os nomes de branch. Em português o texto corrido de `docs/`, o código e os comentários.
- PR e merge (DEC-008): uma PR por task, mesclada com squash pelo humano; cada branch parte de `main` atualizado. O agente não mescla.

## §1 Goals and non-goals

Produto `[HUMAN]`: emissor de NFS-e via API NFS-e Nacional (padrão nacional, gov.br). Fase atual: PoC em Python no Windows (PowerShell, `.venv`).

Objetivo da fase `[HUMAN]`, em ordem:

1. Gerar a DPS em XML.
2. Validar offline contra os XSDs oficiais v1.01 (`schemas/1.01`).
3. Assinar (XMLDSIG).
4. GZip + Base64.
5. Transmitir via mTLS ao ambiente de produção restrita (homologação).

O `README.md` acrescenta dois passos que o contexto da conversa não citou: receber/decodificar a NFS-e de retorno e consultar por chave + baixar o DANFSe. Se entram nesta fase: Q-07.

Non-goals:

- Produção: nada toca produção `[HUMAN]` (DEC-002).
- API (FastAPI): só depois da PoC, segundo o `README.md`.

Critério de sucesso do milestone atual (M1): Q-07 propõe uma redação; não assumi nenhuma.

## §2 Claims policy

O projeto hoje pode afirmar apenas:

| Claim | Evidence |
|---|---|
| Gera um XML de DPS a partir de dataclasses | `src/dps.py`, `tests/test_dps.py` (5 testes passam) |
| O XML de exemplo é válido contra uma cópia local do `DPS_v1.01.xsd` que difere do oficial em uma linha (âncoras do padrão de `serie`) | G-2; `tests/test_xsd.py` (DEC-003) |

Não pode afirmar: que emite NFS-e, que assina, que transmite, que é "válido contra o XSD oficial" sem ressalva, que o servidor aceita a DPS (a DPS de exemplo passa no XSD mas viola a regra E0712 do Anexo I e seria rejeitada; ver T-010), nem qualquer termo da lista do `CLAUDE.md` ("seguro", "pronto para produção" etc.). O `README.md` é um brainstorming e não faz claims desse tipo.

## §3 Architecture

Existente:

```
scripts/gerar_dps.py ──> src/config.py  (lê .env via python-dotenv)
        │
        ├──────────────> src/dps.py     (dataclasses + lxml: modelo, para_xml, validar_xml)
        └──────────────> src/xsd.py     (cópia local dos XSDs sem âncoras)
scripts/preparar_xsd.py ─> src/config.py, src/xsd.py
tests/ ────────────────> src/dps.py, src/xsd.py, src/config.py (só RAIZ)
```

- `src/config.py`: `Config` imutável; `NFSE_AMBIENTE` tem default `homologacao`; `tp_amb` 1=produção, 2=homologação.
- `src/dps.py`: `Prestador`, `Tomador`, `Servico`, `Valores`, `Dps`; `gerar_id`; `para_xml` (sem assinatura); `localizar_xsd_dps`; `validar_xml`.
- `src/xsd.py`: `remover_ancoras`, `dir_local`, `preparar_copia_local`. Gera `schemas/<versão>-local/` (ignorada no git) a partir dos oficiais, tirando só `^` inicial e `$` final dos `xs:pattern`; recusa escrever na pasta de origem (DEC-003).
- `scripts/preparar_xsd.py`: gera a cópia local sob demanda. `scripts/gerar_dps.py` a regenera a cada execução e valida contra ela.

Planejado no `README.md`, ainda inexistente: `certificado.py`, `assinatura.py`, `codec.py`, `client.py`, `erros.py`, `scripts/emitir.py`, `consultar.py`, `baixar_danfse.py`.

Boundaries de dependência: nenhuma definida no repositório. Proposta em Q-08; lista de exceções: vazia.

## §4 Invariants

Aprovados pelo humano em 2026-10-07 (DEC-004).

| ID | Statement | Enforced by |
|---|---|---|
| INV-01 | Os schemas oficiais em `schemas/1.01` nunca são editados | G-3 (`git diff --exit-code main -- schemas/1.00 schemas/1.01`) |
| INV-02 | O ambiente padrão é homologação, e `producao` é recusado pelo código enquanto durar a PoC | Pendente: T-008 (hoje `config.py` tem o default, mas ainda aceita `producao`) |
| INV-03 | Certificados e senhas nunca vão ao git | `.gitignore` (`.env`, `certs/`, `*.pfx`, `*.p12`, `*.pem`); gate pendente: T-008 |
| INV-04 | O `Id` da DPS é `DPS` + 42 dígitos (45 posições): município (7) + tipo de inscrição federal (1) + inscrição federal (14) + série (5) + número da DPS (15) | `test_id_tem_45_caracteres_e_composicao_correta` |

## §5 Interfaces and frozen areas

Decididas pelo humano em 2026-10-07 (DEC-005).

Código e dados frozen (nunca editados):

- `schemas/1.01/` (INV-01), conferido por G-3.

Interfaces frozen (mudam só com nova versão, dados de teste regenerados e nova DEC):

- Formato do XML da DPS: layout v1.01, `versao="1.01"`, namespace `http://www.sped.fazenda.gov.br/nfse`, conforme `DPS_v1.01.xsd`.

Não frozen:

- Variáveis `NFSE_*` de `.env.example`: ainda devem mudar até a transmissão funcionar.
- `schemas/1.00/`: não é usado e será removido do repositório em T-009.

Dados de teste "golden": não existem. `out/` é ignorado no git.

## §6 Dependencies and versions

| Item | Valor observado | Fixado? |
|---|---|---|
| Python | 3.11.9 (`.venv/pyvenv.cfg`) | Não (sem `.python-version`) |
| lxml | 6.1.3 (libxml2 2.11.9, compilada e em execução) | Não |
| python-dotenv | 1.2.4 | Não |
| pytest | 9.1.1 | Não |

- `requirements.txt` lista `lxml`, `python-dotenv`, `pytest` sem versões e não há lockfile: o não-negociável 10 (builds reproduzíveis) não é atendível hoje. Ver T-002.
- `pyvenv.cfg` registra que a venv foi criada em `C:\Users\preis\rpa\nfse-poc\.venv`, outro caminho. `python.exe -m …` funciona; os lançadores `.exe` em `.venv\Scripts` (ex.: `pytest.exe`) podem estar quebrados `[INFERRED]`. Os gates usam `python -m`.
- Bibliotecas ainda não escolhidas (README): HTTP/mTLS (httpx ou requests), `cryptography`, assinatura (signxml ou lxml+xmlsec), nfelib `[HUMAN]` (talvez só para bindings da DPS). Adicionar qualquer uma é decisão de task; adicionar framework/serviço é item de "perguntar".

Itens de verificação:

| Item | Situação |
|---|---|
| Ordem e obrigatoriedade dos elementos da DPS | Parcial: o XML de exemplo valida sem erros contra o XSD v1.01 quando o padrão de `serie` é corrigido numa cópia (checado em 2026-10-07, diagnóstico de §8). Vale só para os elementos que o exemplo emite. Regras de negócio, parcial: o Anexo I (aba `RN DPS_NFS-e`) proíbe `indTotTrib` para emitente ME/EPP (E0712), e o código sempre o emite (checado em 2026-10-07; T-010). `[VERIFY: demais regras de negócio de obrigatoriedade do Anexo I, que o XSD não expressa; só foram lidas as dos campos que o exemplo emite]` |
| `opSimpNac` | 1 Não Optante; 2 MEI; 3 ME/EPP (checado em 2026-10-07, `tiposSimples_v1.01.xsd`, `TSOpSimpNac`) |
| `regEspTrib` | 0 Nenhum; 1 Ato Cooperado; 2 Estimativa; 3 Microempresa Municipal; 4 Notário ou Registrador; 5 Profissional Autônomo; 6 Sociedade de Profissionais; 9 Outros (checado em 2026-10-07, `TSRegEspTrib`) |
| `tribISSQN` | 1 Operação tributável; 2 Imunidade; 3 Exportação de serviço; 4 Não Incidência (checado em 2026-10-07, `TSTribISSQN`) |
| `tpRetISSQN` | 1 Não Retido; 2 Retido pelo Tomador; 3 Retido pelo Intermediário (checado em 2026-10-07, `TSTipoRetISSQN`) |
| Composição do `Id` | "DPS" + Cód.Mun (7) + Tipo de Inscrição Federal (1) + Inscrição Federal (14; CPF com 000 à esquerda) + Série (5) + Núm. DPS (15) = 45 (checado em 2026-10-07, `TSIdDPS`). Tipo de Inscrição Federal: 1 = CPF, 2 = CNPJ do emitente (checado em 2026-10-07, Anexo I v1.01, aba `LEIAUTE DPS_NFS-e`, campo `id`); o código fixa "2" e só aceita prestador com CNPJ |
| URLs dos ambientes | Parcial: o host `adn.producaorestrita.nfse.gov.br` aparece no link do Swagger citado nos manuais dos contribuintes (checado em 2026-10-07; link não acessado). `[VERIFY: URL base da SEFIN em produção restrita e caminhos base das APIs]`. `.env.example` traz `https://sefin.producaorestrita.nfse.gov.br`, sem fonte. Rotas da SEFIN (`POST /nfse`, `GET /nfse/{chaveAcesso}`, `GET`/`HEAD /dps/{id}`): checadas em 2026-10-07, manual do Emissor Público |
| Procedência dos XSDs | `[VERIFY: que os arquivos em schemas/1.01 são o pacote oficial vigente, sem alterações]`. `schemas/LEIAME.md` aponta a página de origem, mas não há data de download nem hash publicado |
| Formato de `serie` no XML | `[VERIFY: se a série vai como "1" ou "00001"]`. O XSD aceita os dois; o `Id` usa 5 dígitos. O Anexo I só diz "numérico, tamanho 1-5" e não resolve; confirmar na primeira transmissão (Q-11) |
| Faixa de `serie` | 00001 a 49999 para aplicativo próprio; fora da faixa do emissor, rejeição E0010 (checado em 2026-10-07, Anexo I v1.01). O modelo hoje aceita 1 a 99999 (Q-12) |

Todas as checagens "no XSD" valem para os arquivos locais, e dependem do item de procedência.

## §7 Security and secrets

- Segredos vêm de `.env` (ignorado no git) via `python-dotenv`: `NFSE_CERT_PATH`, `NFSE_CERT_PASSWORD`.
- Ambientes: `homologacao` (default; "produção restrita") e `producao`. `producao` é um valor aceito por `config.py`; não há trava além do default.
- Nenhum segredo encontrado no histórico: `git ls-files` não contém `.env`, `.pfx`, `.p12` nem `.pem`.
- **Observação**: existe `certs/lika-2026.pfx` (8.719 bytes, ignorado no git) e o `.env` local tem `NFSE_CERT_PATH` apontando para ele e `NFSE_CERT_PASSWORD` preenchida. O contexto da conversa dizia que ainda não há certificado A1. Não abri o arquivo nem li a senha. Ver Q-03.
- Modelo de confiança, uso de certificado de terceiro e tratamento de dados pessoais (CNPJ/CPF de tomadores em `out/`): não definidos; Q-03.
- Os dados de exemplo em `scripts/gerar_dps.py` e nos testes estão marcados como fictícios no código.

## §8 Gates

Comandos em PowerShell, a partir da raiz. Não há CI, Makefile nem scripts de verificação no repositório; os gates abaixo vêm do que o projeto já executa.

Preparação a partir de um checkout limpo (hoje **não** reproduzível, ver T-002):

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

| ID | Gate | Command | When |
|---|---|---|---|
| G-1 | Testes | `.\.venv\Scripts\python.exe -m pytest -q -rs` | Toda task |
| G-2 | Verificação do projeto: gerar e validar a DPS | `.\.venv\Scripts\python.exe scripts\gerar_dps.py` (sucesso = código de saída 0) | Toda task |
| G-3 | XSDs oficiais intocados | `git diff --exit-code main -- schemas/1.00 schemas/1.01` | Toda task |
| – | Formatação | inexistente | proposta em T-003 |
| – | Lint com avisos como erro | inexistente | proposta em T-003 |
| – | Instalação travada / build | inexistente | proposta em T-002 |

### Baseline (2026-10-07, commit `4abfc2c`, Python 3.11.9, lxml 6.1.3)

**G-1: passa, mas esconde a falha.** `5 passed, 1 skipped`. O teste pulado é `test_xml_valido_contra_xsd_oficial`: ele procura `DPS_v*.xsd` em `schemas/`, e os arquivos estão em `schemas/1.01/`, então a condição de `skipif` é sempre verdadeira.

**G-2: falha, código de saída 1.**

```
[X] Inválida contra DPS_v1.01.xsd:
   - linha 2: Element '{http://www.sped.fazenda.gov.br/nfse}serie': [facet 'pattern'] The value '1' is not accepted by the pattern '^0{0,4}\d{1,5}$'.
```

G-2 depende do `.env` local (`NFSE_XSD_DIR=schemas/1.01`). Com o `.env.example` sem ajuste (`NFSE_XSD_DIR=schemas`) o script não acha o XSD e sai com código 2 `[INFERRED]` (lido no código, não executado).

### Depois de T-001 (2026-10-07, branch `t-001-validacao-serie-xsd`)

- G-1: `26 passed`, nenhum pulado.
- G-2: código de saída 0, `[OK] Válida contra DPS_v1.01.xsd (cópia local em …\schemas.01-local)`. Também sai com 0 sem `.env` (executado), porque o default de `NFSE_XSD_DIR` passou a ser `schemas/1.01`.
- G-3: sem diferenças.

### Fechamento da T-001 (2026-10-07, mesma branch)

Reexecutados antes e depois de atualizar o spec e as fontes com a documentação de `docs/referencia/`, com o mesmo resultado: G-1 `26 passed`, nenhum pulado; G-2 código de saída 0, `[OK] Válida contra DPS_v1.01.xsd`; G-3 sem diferenças.

### Diagnóstico da falha de G-2 (hipótese confirmada)

1. **Norma.** XML Schema Part 2, Apêndice F: as expressões regulares são ancoradas implicitamente no início e no fim; `^` e `$` não são metacaracteres (`^` só tem papel especial dentro de `[...]`). Num `xs:pattern`, portanto, são caracteres literais.
2. **Comportamento do libxml2 2.11.9 (via lxml 6.1.3).** Esquema mínimo com o mesmo padrão: `^0{0,4}\d{1,5}$` rejeita `1` e `00001` e aceita os textos literais `^1$` e `^00001$`. Sem as âncoras, aceita `1` e `00001` e rejeita `^1$` e `abc`.
3. **Alcance.** Dos 54 `xs:pattern` em `schemas/1.01`, só um tem âncoras: `TSSerieDPS`, `tiposSimples_v1.01.xsd` linha 161. Em `schemas/1.00` não há nenhum.
4. **Efeito da correção.** Com uma cópia dos XSDs fora do repositório, trocando só esse padrão por `0{0,4}\d{1,5}`, a DPS de exemplo valida com 0 erros. Não há outra falha escondida atrás desta para o XML de exemplo.

Consequência: nenhum valor de `serie` que a API aceitaria passa no XSD oficial com um validador conforme a norma. O validador do servidor provavelmente usa um motor que trata `^`/`$` como âncoras `[INFERRED]`; validar offline contra uma cópia corrigida não prova que o servidor aceita.

## §9 Milestones and tasks

Milestones `[INFERRED]` a partir do objetivo da fase; confirmar em Q-07.

- **M1**: DPS gerada e válida offline contra o XSD v1.01.
- **M2**: DPS assinada e empacotada (XMLDSIG, GZip+Base64).
- **M3**: transmissão via mTLS em produção restrita.

Phase gates: toda PR é um phase gate (decisão do humano em 2026-10-07). Cada task para em `review` e só vai a `done` depois da revisão do humano.

| ID    | Title | Deps | Reads | Status | Acceptance criteria |
|-------|--------|------|-------|--------|------------------------|
| T-000 | Bootstrap: spec, fontes e baseline | – | CLAUDE.md | done | `docs/SPEC.md` e `docs/SOURCES.md` no branch `t-000-spec`; baseline de G-1 e G-2 registrado; humano escreve `Approved:` em §0 |
| T-001 | Validação offline da DPS falha no padrão de `serie` | T-000, Q-01, Q-04 | §4, §5, §6, §8 | done | (1) G-2 sai com código 0 e imprime `[OK] Válida`; (2) `test_xml_valido_contra_xsd_oficial` deixa de ser pulado e passa; (3) `git diff main -- schemas/1.00 schemas/1.01` vazio; (4) teste negativo: `serie` inválida (ex.: `abc`, 6 dígitos) continua rejeitada pelo esquema usado na validação; (5) se houver cópia derivada: é regenerável por script, ignorada no git, e um teste garante que ela difere dos oficiais só nas âncoras `^`/`$` de início e fim de `xs:pattern` (hoje, 1 linha); (6) `.env.example` e o default de `NFSE_XSD_DIR` coerentes com o local real dos XSDs |
| T-002 | Fixar toolchain e dependências | T-000 | §6, §8 | todo | Versão do Python fixada; dependências com versões exatas e lock; instalação travada documentada em §8 e funcionando em checkout limpo. Ferramenta de lock: Q-05 |
| T-003 | Propor gates de formatação e lint | T-000 | §8 | todo | Proposta apresentada ao humano (ferramenta, regras, custo); nada instalado sem aprovação (Q-05) |
| T-004 | Certificado A1: carregar PFX (`certificado.py`) | T-001, Q-03 | §7 | blocked (Q-03) | A definir com o humano |
| T-005 | Assinatura XMLDSIG (`assinatura.py`) | T-004, Q-06 | §5, §6 | todo | A definir; exige `[VERIFY]` do perfil de assinatura exigido pelo padrão nacional |
| T-006 | Codec GZip+Base64 (`codec.py`) | T-001 | §5 | todo | A definir; ida e volta sem perda |
| T-008 | Garantias de INV-02 e INV-03 | T-001 | §4, §7, §8 | todo | (1) `carregar_config()` sem variáveis de ambiente devolve `homologacao`; (2) `NFSE_AMBIENTE=producao` levanta erro claro citando DEC-002/INV-02; (3) gate novo em §8 que falha se `git ls-files` contiver `.env`, `*.pfx`, `*.p12` ou `*.pem`; (4) `.env.example` deixa de anunciar `producao` como opção |
| T-009 | Remover `schemas/1.00` do repositório | T-001 | §5, §8 | todo | (1) `schemas/1.00/` removido do git; (2) G-3 passa a conferir só `schemas/1.01`; (3) `schemas/LEIAME.md` e `docs/SOURCES.md` coerentes com a remoção; (4) G-1 e G-2 continuam passando |
| T-010 | `totTrib` para emitente ME/EPP (E0712) | T-001, Q-13 | §5, §6 | todo | (1) com `op_simp_nac=3` o XML não contém `indTotTrib` e emite outra opção da escolha `totTrib` (qual: Q-13); (2) para não optante o XML continua válido; (3) os dois casos válidos contra a cópia local dos XSDs; (4) teste negativo: a combinação ME/EPP + `indTotTrib` não é gerada |
| T-007 | Cliente mTLS e erros (`client.py`, `erros.py`) | T-004, T-005, T-006, T-010 | §6, §7 | todo | A definir; exige `[VERIFY]` de URLs e rotas; só produção restrita |
| T-011 | Termos do `CLAUDE.md` em inglês e regras básicas do projeto | T-001 | CLAUDE.md, §0, §9, §10 | done | (1) títulos de seção, colunas e termos do spec em inglês, conforme DEC-006; (2) §0 com as regras de idioma, de `Approved`/`done` e de PR e merge; (3) DEC-006 a DEC-009 registradas; (4) nenhum arquivo fora de `docs/` alterado; (5) G-1 a G-3 passam |

### Ponto de retomada (2026-10-07)

Estado ao fim da sessão de 2026-10-07, para continuar em outra máquina:

- T-000 e T-001 em `review`, aguardando o humano marcar `done`. Branches `t-000-spec` e `t-001-validacao-serie-xsd` publicadas em `origin`; `main` só tem o commit inicial.
- §11 respondidas: Q-01, Q-02, Q-04. Parcial: Q-03. Ainda não discutidas: Q-05 a Q-11, nessa ordem.
- Tasks criadas e não iniciadas: T-008 (trava de `producao` e gate de segredos), T-009 (remover `schemas/1.00`).
- O humano já tem, fora do repositório: a documentação oficial (PDFs e planilhas) e uma nota fiscal antiga do cliente. Destino combinado: documentação em `docs/referencia/` (ignorada no git); nota fiscal em `certs/` ou `out/` (ignoradas), por conter dados reais. Com elas dá para fechar os `[VERIFY]` de §6 e montar os dados reais do prestador, que ficam em arquivo local fora do git, nunca no código nem nos testes.
- Atualização no fechamento da T-001 (2026-10-07): a documentação oficial e a nota de exemplo já estão em `docs/referencia/` (ignorada no git). Com ela foram fechados o Tipo de Inscrição Federal do `Id` e a faixa de `serie`, e registradas as rotas da SEFIN e as regras de recepção (§6, `docs/SOURCES.md`). Seguem abertos: formato de `serie` no XML, URL base da SEFIN, procedência dos XSDs. Lacuna nova: E0712 (T-010). Open questions novas: Q-12 e Q-13. Os dados reais do prestador ainda não foram montados em arquivo local.
- T-000 e T-001 marcadas `done` pelo humano na conversa de 2026-10-07 (status transcrito pelo agente a pedido dele). As branches ainda não foram mescladas em `main`.
- Atualização em T-011 (2026-10-07): T-000 e T-001 entraram em `main` pela PR #1, com squash, no commit `65c2e9b`. As branches `t-000-spec` e `t-001-validacao-serie-xsd` ficaram obsoletas. Próxima task pela ordem da DEC-009: T-008. Open questions sem resposta: Q-05 a Q-10, Q-12 e Q-13; parciais: Q-03 e Q-11.
- T-011 entrou em `main` pela PR #2 (`b9c6e52`) e foi marcada `done` pelo humano na conversa de 2026-10-07 (transcrito pelo agente, DEC-007).
- Não viajam pelo git e precisam ser recriados na outra máquina: `.venv`, `.env` (copiar de `.env.example`), `certs/*.pfx` e a senha, chave SSH, `git config user.name`/`user.email`, `docs/referencia/`. `schemas/1.01-local` é regenerada por `scripts/gerar_dps.py`.

## §10 Decision log

### DEC-001: Dataclasses em vez de pydantic para o modelo da DPS (2026-10-07, T-000)
Context: o `README.md` lista pydantic como candidata; o código usa `dataclasses` + lxml.
Decision: dataclasses. Decisão do humano, informada na conversa de 2026-10-07.
Alternatives: pydantic (README); nfelib para bindings da DPS (ainda em aberto, Q-06).
Consequences: o README fica desatualizado nesse ponto (Q-09). §3.

### DEC-002: Nada de produção nesta fase (2026-10-07, T-000)
Context: a API tem produção e produção restrita; `config.py` aceita `producao`.
Decision: a PoC só usa produção restrita (homologação). Decisão do humano, informada na conversa de 2026-10-07.
Alternatives: nenhuma considerada.
Consequences: §1, §7. Virou INV-02, com trava em código a implementar em T-008.

### DEC-003: Validação offline contra cópia local dos XSDs, sem âncoras (2026-10-07, T-001)
Context: o padrão de `TSSerieDPS` no XSD oficial v1.01 traz `^` e `$`, literais em XML Schema, e o libxml2 rejeita qualquer série (§8, diagnóstico). Os oficiais não devem ser editados (candidato C-1).
Decision: plano (a) de Q-04, escolhido pelo humano em 2026-10-07: cópia gerada em `schemas/1.01-local`, ignorada no git. Escolhas de implementação do agente: a lógica fica em `src/xsd.py` e opera em bytes (preserva BOM e CRLF); remove só `^` no início e `$` não escapado no fim do valor de `xs:pattern`; `gerar_dps.py` regenera a cópia a cada execução, para ela nunca ficar desatualizada; os testes geram a cópia em diretório temporário; `scripts/preparar_xsd.py` (antes não rastreado) foi reescrito como casca fina sobre `src/xsd.py`; `.gitignore` ganhou `schemas/*-local/`; o default de `NFSE_XSD_DIR` e o `.env.example` passaram a `schemas/1.01`; G-3 entrou em §8.
Alternatives: (b) corrigir em memória ao carregar o esquema: sem arquivo derivado, mas exigiria um resolvedor próprio para os `xs:include` e não deixa a diferença inspecionável em disco. Editar os oficiais: rejeitado (C-1).
Consequences: "válida" passa a significar válida contra a cópia local, que um teste fixa em exatamente uma linha de diferença (`tiposSimples_v1.01.xsd:161`); uma nova versão do pacote oficial que mude isso quebra o teste de propósito. Não prova aceitação pelo servidor. §2, §3, §8, §9, §11 atualizados.

### DEC-004: Invariantes INV-01 a INV-04 aprovados (2026-10-07, T-000)
Context: os quatro candidatos de Q-01 aguardavam decisão; nenhum invariante estava em vigor.
Decision: do humano, na conversa de 2026-10-07: aprovar os quatro. INV-02 vai além do default: o código recusa `producao` durante a PoC. INV-04 usa a redação completa do XSD (`TSIdDPS`), não só "45 caracteres".
Alternatives: INV-02 só com o default (rejeitado: bastaria uma linha no `.env` para apontar para produção); INV-04 só com o tamanho.
Consequences: §0, §4, §9 (T-008 criada para as garantias que faltam), §11. Liberar produção no futuro exige nova DEC.

### DEC-005: Áreas e interfaces congeladas (2026-10-07, T-000)
Context: Q-02 perguntava o que congelar em §5; `schemas/1.00` estava versionado sem uso e havia duas pastas vazias não rastreadas em `schemas/`.
Decision: do humano, na conversa de 2026-10-07: congelar `schemas/1.01` (já INV-01) e o formato do XML da DPS em v1.01; remover `schemas/1.00` do repositório (T-009); apagar as pastas vazias `schemas/Componente_Schemas` e `schemas/Componente_recepcao` (apagadas nesta data; não eram rastreadas).
Alternatives: congelar `schemas/1.00` junto (rejeitado: material sem uso); congelar também as variáveis `NFSE_*` (adiado: ainda vão mudar).
Consequences: §5, §9 (T-009), §11. Trocar a versão do layout da DPS passa a exigir nova DEC.

### DEC-006: Termos do `CLAUDE.md`, commits e PRs em inglês (2026-10-07, T-011)
Context: o spec traduziu os termos do `CLAUDE.md` ("portões", "marcos", "invariantes"), o que criou dois vocabulários para a mesma coisa; os commits até `65c2e9b` estão em português.
Decision: do humano, na conversa de 2026-10-07: ficam em inglês os termos do `CLAUDE.md`, os títulos de seção e de coluna do spec, as mensagens de commit, os títulos e textos de PR e os nomes de branch. O texto corrido de `docs/`, o código e os comentários continuam em português.
Alternatives: traduzir o spec inteiro (rejeitado: reescrita grande sem ganho para a PoC); escrever também o código novo em inglês (rejeitado: misturaria dois idiomas com o código existente).
Consequences: §0 a §9 e §11 renomeados nesta task. As DEC-001 a DEC-005 não foram reescritas, porque este log só cresce, e mantêm os termos antigos: "portão" = gate, "marco" = milestone, "invariante" = invariant, "tarefa" = task, "congelado" = frozen, "fronteira" = boundary, "alegação" = claim. A marca `[HUMANO]` passou a `[HUMAN]`. O histórico de commits anterior não é reescrito.

### DEC-007: O agente transcreve `Approved` e `done` a pedido do humano (2026-10-07, T-011)
Context: o `CLAUDE.md` diz que o spec está aprovado quando o humano escreve `Approved:` e que só o humano marca uma task como `done`. Em 2026-10-07 o agente transcreveu as duas marcas (§0; T-000 e T-001) a pedido do humano, sem uma DEC que relaxasse a regra.
Decision: do humano, na conversa de 2026-10-07: o agente pode escrever `Approved` e `done` quando o humano pedir explicitamente na conversa, e anota a data e que foi transcrição. O agente nunca deduz uma aprovação de um comentário indireto.
Alternatives: só o humano edita o arquivo à mão (regra original; rejeitada pelo humano).
Consequences: §0. Regulariza as transcrições já feitas nesta data.

### DEC-008: Uma PR por task, com squash, a partir de `main` (2026-10-07, T-011)
Context: o `CLAUDE.md` manda empilhar as PRs dentro de um milestone. O humano quer um commit por task em `main`, e o squash de PRs empilhadas gera conflito na PR seguinte. T-000 e T-001 já entraram juntas em `main` pela PR #1, num commit único (`65c2e9b`), exceção a "uma PR por task" decidida pelo humano.
Decision: do humano, na conversa de 2026-10-07: cada task tem a sua branch, criada a partir de `main` atualizado, e a sua PR, mesclada com squash pelo humano. O agente não mescla.
Alternatives: uma PR por milestone com squash (rejeitado: `main` ficaria muito tempo sem o trabalho em andamento); merge commit com PRs empilhadas, como no `CLAUDE.md` (rejeitado: o humano quer um commit por task).
Consequences: §0. Uma task só começa quando as tasks de que depende já estão em `main`. G-3 continua comparando com `main`. Enquanto não houver `gh` na máquina, o agente entrega o link de comparação, o título e a descrição, e o humano abre a PR.

### DEC-009: Ordem das próximas tasks (2026-10-07, T-011)
Context: pela regra do `CLAUDE.md` (menor ID elegível) a próxima task seria T-002, que depende de Q-05. T-008 dá garantia a INV-02 e INV-03, não depende de nenhuma open question e deve vir antes de qualquer uso do certificado real.
Decision: do humano, no plano aprovado em 2026-10-07: T-008, T-002, T-009, T-003, T-010, T-006, T-004, T-005, T-007. Uma task bloqueada por open question espera, e segue a próxima da lista. T-011 foi feita antes de todas, a pedido do humano.
Alternatives: seguir o menor ID elegível (rejeitado: deixaria a trava de `producao` para depois).
Consequences: §9. A ordem vale até o humano nomear outra task.

## §11 Open questions

| ID | Question | Blocks |
|---|---|---|
| Q-01 | **Respondida em 2026-10-07: os quatro aprovados, ver §4 e DEC-004.** Aprovar, ajustar ou rejeitar cada candidato a invariant de §4 (C-1 schemas oficiais intocados; C-2 default homologação; C-3 certificados e senhas fora do git; C-4 `Id` com 45 caracteres). Para C-2: basta o default, ou `producao` deve exigir uma confirmação explícita extra (ou ser recusado nesta fase, dado DEC-002)? | T-001, todas |
| Q-02 | **Respondida em 2026-10-07, ver §5 e DEC-005.** O que fica frozen em §5: `schemas/1.01`? também `schemas/1.00` (não usado), ou removê-lo? As pastas vazias `schemas/Componente_Schemas` e `schemas/Componente_recepcao` (não rastreadas) têm algum uso? | T-001 |
| Q-03 | **Parcial em 2026-10-07:** o humano confirmou que `lika-2026.pfx` é o certificado do cliente e que o titular autorizou o uso em produção restrita. Faltam duas respostas: (a) desenvolver T-004 e T-005 com certificado autoassinado de teste, deixando o do cliente só para T-007? (b) só dados fictícios nos testes automatizados e nunca senha ou conteúdo de certificado em logs? Texto original: Certificado: `certs/lika-2026.pfx` já existe e o `.env` tem senha, mas o contexto dizia que ainda não há A1. É o certificado do cliente? Há autorização do titular para uso em homologação? Onde a DPS de teste pode ser emitida (CNPJ do titular)? Como tratar dados reais em `out/` e em logs? | T-004, T-007 |
| Q-04 | **Respondida em 2026-10-07: (a), ver DEC-003.** T-001, abordagem: (a) cópia gerada `schemas/1.01-local`, ignorada no git, com script e teste de diferença mínima (seu plano; recomendo, restringindo a remoção às âncoras de início/fim); (b) corrigir em memória ao carregar o esquema, sem arquivo derivado. Em (a), `scripts/preparar_xsd.py` (não rastreado) entra como base? E `.gitignore` ganha `schemas/*-local/`? | T-001 |
| Q-05 | Ferramentas a adicionar: lock (pip-tools, uv, `pip freeze` com hashes), formatador e linter (ex.: ruff), CI (GitHub Actions; há remoto `origin` no GitHub). | T-002, T-003 |
| Q-06 | Bibliotecas: nfelib só para bindings da DPS, ou manter o modelo próprio? Assinatura: signxml ou lxml+xmlsec? HTTP: httpx ou requests? | T-005, T-007 |
| Q-07 | Escopo e milestones: M1–M3 de §9 estão certos? Os passos 4 e 5 do README (decodificar retorno; consulta por chave e DANFSe) entram nesta fase? Critério de sucesso de M1 proposto: "G-1 e G-2 passam, com o teste de XSD rodando". | planejamento |
| Q-08 | Boundaries de §3. Proposta: `src/dps.py` não depende de rede nem de certificado; só `client.py` faz I/O de rede; `scripts/` depende de `src/`, nunca o contrário. | T-004 em diante |
| Q-09 | Conflitos com o README: cita pydantic (contra DEC-001) e é um brainstorming, não uma descrição do projeto. Atualizar numa task própria? | – |
| Q-10 | Licença: não há `LICENSE`. O remoto é `github.com/prbn021/nfse-poc`; se for público, o repositório redistribui os XSDs oficiais. Qual licença, e os XSDs podem ficar versionados? | cópia de código de terceiros |
| Q-11 | **Parcial em 2026-10-07:** o defeito do XSD fica só registrado no spec (§8, DEC-003), sem reporte. O formato segue aberto: o Anexo I diz apenas "numérico, tamanho 1-5"; confirmar na primeira transmissão em produção restrita. Texto original: Formato de `serie` no XML ("1" ou "00001") e a quem reportar o defeito do padrão no XSD oficial (se quiser reportar). | T-007 |
| Q-12 | Restringir `serie` no modelo a 1–49999? O Anexo I reserva essa faixa ao aplicativo próprio e rejeita o resto com E0010; `Dps` hoje aceita até 99999. | – |
| Q-13 | Emitente ME/EPP: (a) qual opção de `totTrib` emitir no lugar de `indTotTrib` (`pTotTribSN`, ou `vTotTrib`/`pTotTrib`)? (b) emitir `regApTribSN`, que o modelo hoje não tem? (c) o exemplo e os testes devem espelhar o perfil do cliente (ME/EPP, tomador pessoa física, sem inscrição municipal), sempre com dados fictícios (liga com Q-03b)? | T-010 |
