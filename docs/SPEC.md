# SPEC: nfse-poc

Rascunho gerado no Bootstrap (T-000) em 2026-10-07. Marcações:

- sem marca: observado no repositório ou executado nesta data;
- `[HUMANO]`: informado pelo humano na conversa de 2026-10-07, não confirmável pelo repositório;
- `[INFERRED]`: deduzido por mim, não observado diretamente;
- `[VERIFY: …]`: ainda não checado; nenhum código pode depender disso antes da checagem.

## §0 Regras para agentes

Approved: 2026-10-07

(Aprovação dada pelo humano na conversa de 2026-10-07 e transcrita aqui pelo agente. A aprovação cobre o spec; os candidatos a invariante de §4 continuam pendentes em Q-01.)

- Quem aprova: Paulo Reis (único autor em `git log`) aprova o spec, os invariantes, os portões de fase e é o único que marca tarefas como `done`.
- Regras específicas do projeto, além do `CLAUDE.md`: os invariantes de §4.
- Idioma: docs, código e mensagens em português, como no repositório existente `[INFERRED]`.

## §1 Objetivos e não-objetivos

Produto `[HUMANO]`: emissor de NFS-e via API NFS-e Nacional (padrão nacional, gov.br). Fase atual: PoC em Python no Windows (PowerShell, `.venv`).

Objetivo da fase `[HUMANO]`, em ordem:

1. Gerar a DPS em XML.
2. Validar offline contra os XSDs oficiais v1.01 (`schemas/1.01`).
3. Assinar (XMLDSIG).
4. GZip + Base64.
5. Transmitir via mTLS ao ambiente de produção restrita (homologação).

O `README.md` acrescenta dois passos que o contexto da conversa não citou: receber/decodificar a NFS-e de retorno e consultar por chave + baixar o DANFSe. Se entram nesta fase: Q-07.

Não-objetivos:

- Produção: nada toca produção `[HUMANO]` (DEC-002).
- API (FastAPI): só depois da PoC, segundo o `README.md`.

Critério de sucesso do marco atual (M1): Q-07 propõe uma redação; não assumi nenhuma.

## §2 Política de alegações

O projeto hoje pode afirmar apenas:

| Alegação | Evidência |
|---|---|
| Gera um XML de DPS a partir de dataclasses | `src/dps.py`, `tests/test_dps.py` (5 testes passam) |
| O XML de exemplo é válido contra uma cópia local do `DPS_v1.01.xsd` que difere do oficial em uma linha (âncoras do padrão de `serie`) | G-2; `tests/test_xsd.py` (DEC-003) |

Não pode afirmar: que emite NFS-e, que assina, que transmite, que é "válido contra o XSD oficial" sem ressalva, que o servidor aceita a DPS, nem qualquer termo da lista do `CLAUDE.md` ("seguro", "pronto para produção" etc.). O `README.md` é um brainstorming e não faz alegações desse tipo.

## §3 Arquitetura

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

Fronteiras de dependência: nenhuma definida no repositório. Proposta em Q-08; lista de exceções: vazia.

## §4 Invariantes

Aprovados pelo humano em 2026-10-07 (DEC-004).

| ID | Enunciado | Garantido por |
|---|---|---|
| INV-01 | Os schemas oficiais em `schemas/1.01` nunca são editados | G-3 (`git diff --exit-code main -- schemas/1.00 schemas/1.01`) |
| INV-02 | O ambiente padrão é homologação, e `producao` é recusado pelo código enquanto durar a PoC | Pendente: T-008 (hoje `config.py` tem o default, mas ainda aceita `producao`) |
| INV-03 | Certificados e senhas nunca vão ao git | `.gitignore` (`.env`, `certs/`, `*.pfx`, `*.p12`, `*.pem`); portão pendente: T-008 |
| INV-04 | O `Id` da DPS é `DPS` + 42 dígitos (45 posições): município (7) + tipo de inscrição federal (1) + inscrição federal (14) + série (5) + número da DPS (15) | `test_id_tem_45_caracteres_e_composicao_correta` |

## §5 Interfaces e áreas congeladas

Nada está congelado até a aprovação. Candidatos (Q-02):

- Código/dados congelados: `schemas/1.01/` (C-1). `schemas/1.00/` também está rastreado e não é usado por nenhum código: congelar, ou remover?
- Interface: formato do XML da DPS, ditado pelo XSD v1.01 (`versao="1.01"`, namespace `http://www.sped.fazenda.gov.br/nfse`).
- Configuração: variáveis `NFSE_*` em `.env.example`.
- Dados de teste "golden": não existem. `out/` é ignorado no git.

## §6 Dependências e versões

| Item | Valor observado | Fixado? |
|---|---|---|
| Python | 3.11.9 (`.venv/pyvenv.cfg`) | Não (sem `.python-version`) |
| lxml | 6.1.3 (libxml2 2.11.9, compilada e em execução) | Não |
| python-dotenv | 1.2.4 | Não |
| pytest | 9.1.1 | Não |

- `requirements.txt` lista `lxml`, `python-dotenv`, `pytest` sem versões e não há lockfile: o não-negociável 10 (builds reproduzíveis) não é atendível hoje. Ver T-002.
- `pyvenv.cfg` registra que a venv foi criada em `C:\Users\preis\rpa\nfse-poc\.venv`, outro caminho. `python.exe -m …` funciona; os lançadores `.exe` em `.venv\Scripts` (ex.: `pytest.exe`) podem estar quebrados `[INFERRED]`. Os portões usam `python -m`.
- Bibliotecas ainda não escolhidas (README): HTTP/mTLS (httpx ou requests), `cryptography`, assinatura (signxml ou lxml+xmlsec), nfelib `[HUMANO]` (talvez só para bindings da DPS). Adicionar qualquer uma é decisão de tarefa; adicionar framework/serviço é item de "perguntar".

Itens de verificação:

| Item | Situação |
|---|---|
| Ordem e obrigatoriedade dos elementos da DPS | Parcial: o XML de exemplo valida sem erros contra o XSD v1.01 quando o padrão de `serie` é corrigido numa cópia (checado em 2026-10-07, diagnóstico de §8). Vale só para os elementos que o exemplo emite. `[VERIFY: regras de negócio de obrigatoriedade no manual/anexos, que o XSD não expressa]` |
| `opSimpNac` | 1 Não Optante; 2 MEI; 3 ME/EPP (checado em 2026-10-07, `tiposSimples_v1.01.xsd`, `TSOpSimpNac`) |
| `regEspTrib` | 0 Nenhum; 1 Ato Cooperado; 2 Estimativa; 3 Microempresa Municipal; 4 Notário ou Registrador; 5 Profissional Autônomo; 6 Sociedade de Profissionais; 9 Outros (checado em 2026-10-07, `TSRegEspTrib`) |
| `tribISSQN` | 1 Operação tributável; 2 Imunidade; 3 Exportação de serviço; 4 Não Incidência (checado em 2026-10-07, `TSTribISSQN`) |
| `tpRetISSQN` | 1 Não Retido; 2 Retido pelo Tomador; 3 Retido pelo Intermediário (checado em 2026-10-07, `TSTipoRetISSQN`) |
| Composição do `Id` | "DPS" + Cód.Mun (7) + Tipo de Inscrição Federal (1) + Inscrição Federal (14; CPF com 000 à esquerda) + Série (5) + Núm. DPS (15) = 45 (checado em 2026-10-07, `TSIdDPS`). `[VERIFY: valores do Tipo de Inscrição Federal; o código fixa "2" para CNPJ]` |
| URLs dos ambientes | `[VERIFY: URLs de SEFIN e ADN em produção restrita]`. `.env.example` traz `https://sefin.producaorestrita.nfse.gov.br` e `https://adn.producaorestrita.nfse.gov.br`, sem fonte |
| Procedência dos XSDs | `[VERIFY: que os arquivos em schemas/1.01 são o pacote oficial vigente, sem alterações]`. `schemas/LEIAME.md` aponta a página de origem, mas não há data de download nem hash publicado |
| Formato de `serie` no XML | `[VERIFY: se a série vai como "1" ou "00001"]`. O XSD aceita os dois; o `Id` usa 5 dígitos |

Todas as checagens "no XSD" valem para os arquivos locais, e dependem do item de procedência.

## §7 Segurança e segredos

- Segredos vêm de `.env` (ignorado no git) via `python-dotenv`: `NFSE_CERT_PATH`, `NFSE_CERT_PASSWORD`.
- Ambientes: `homologacao` (default; "produção restrita") e `producao`. `producao` é um valor aceito por `config.py`; não há trava além do default.
- Nenhum segredo encontrado no histórico: `git ls-files` não contém `.env`, `.pfx`, `.p12` nem `.pem`.
- **Observação**: existe `certs/lika-2026.pfx` (8.719 bytes, ignorado no git) e o `.env` local tem `NFSE_CERT_PATH` apontando para ele e `NFSE_CERT_PASSWORD` preenchida. O contexto da conversa dizia que ainda não há certificado A1. Não abri o arquivo nem li a senha. Ver Q-03.
- Modelo de confiança, uso de certificado de terceiro e tratamento de dados pessoais (CNPJ/CPF de tomadores em `out/`): não definidos; Q-03.
- Os dados de exemplo em `scripts/gerar_dps.py` e nos testes estão marcados como fictícios no código.

## §8 Portões

Comandos em PowerShell, a partir da raiz. Não há CI, Makefile nem scripts de verificação no repositório; os portões abaixo vêm do que o projeto já executa.

Preparação a partir de um checkout limpo (hoje **não** reproduzível, ver T-002):

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

| ID | Portão | Comando | Quando |
|---|---|---|---|
| G-1 | Testes | `.\.venv\Scripts\python.exe -m pytest -q -rs` | Toda tarefa |
| G-2 | Verificação do projeto: gerar e validar a DPS | `.\.venv\Scripts\python.exe scripts\gerar_dps.py` (sucesso = código de saída 0) | Toda tarefa |
| G-3 | XSDs oficiais intocados | `git diff --exit-code main -- schemas/1.00 schemas/1.01` | Toda tarefa |
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

### Diagnóstico da falha de G-2 (hipótese confirmada)

1. **Norma.** XML Schema Part 2, Apêndice F: as expressões regulares são ancoradas implicitamente no início e no fim; `^` e `$` não são metacaracteres (`^` só tem papel especial dentro de `[...]`). Num `xs:pattern`, portanto, são caracteres literais.
2. **Comportamento do libxml2 2.11.9 (via lxml 6.1.3).** Esquema mínimo com o mesmo padrão: `^0{0,4}\d{1,5}$` rejeita `1` e `00001` e aceita os textos literais `^1$` e `^00001$`. Sem as âncoras, aceita `1` e `00001` e rejeita `^1$` e `abc`.
3. **Alcance.** Dos 54 `xs:pattern` em `schemas/1.01`, só um tem âncoras: `TSSerieDPS`, `tiposSimples_v1.01.xsd` linha 161. Em `schemas/1.00` não há nenhum.
4. **Efeito da correção.** Com uma cópia dos XSDs fora do repositório, trocando só esse padrão por `0{0,4}\d{1,5}`, a DPS de exemplo valida com 0 erros. Não há outra falha escondida atrás desta para o XML de exemplo.

Consequência: nenhum valor de `serie` que a API aceitaria passa no XSD oficial com um validador conforme a norma. O validador do servidor provavelmente usa um motor que trata `^`/`$` como âncoras `[INFERRED]`; validar offline contra uma cópia corrigida não prova que o servidor aceita.

## §9 Marcos e tarefas

Marcos `[INFERRED]` a partir do objetivo da fase; confirmar em Q-07.

- **M1**: DPS gerada e válida offline contra o XSD v1.01.
- **M2**: DPS assinada e empacotada (XMLDSIG, GZip+Base64).
- **M3**: transmissão via mTLS em produção restrita.

Portões de fase: nenhum definido; até lá, todo PR é um portão.

| ID    | Título | Deps | Reads | Status | Critérios de aceitação |
|-------|--------|------|-------|--------|------------------------|
| T-000 | Bootstrap: spec, fontes e baseline | – | CLAUDE.md | review | `docs/SPEC.md` e `docs/SOURCES.md` no branch `t-000-spec`; baseline de G-1 e G-2 registrado; humano escreve `Approved:` em §0 |
| T-001 | Validação offline da DPS falha no padrão de `serie` | T-000, Q-01, Q-04 | §4, §5, §6, §8 | review | (1) G-2 sai com código 0 e imprime `[OK] Válida`; (2) `test_xml_valido_contra_xsd_oficial` deixa de ser pulado e passa; (3) `git diff main -- schemas/1.00 schemas/1.01` vazio; (4) teste negativo: `serie` inválida (ex.: `abc`, 6 dígitos) continua rejeitada pelo esquema usado na validação; (5) se houver cópia derivada: é regenerável por script, ignorada no git, e um teste garante que ela difere dos oficiais só nas âncoras `^`/`$` de início e fim de `xs:pattern` (hoje, 1 linha); (6) `.env.example` e o default de `NFSE_XSD_DIR` coerentes com o local real dos XSDs |
| T-002 | Fixar toolchain e dependências | T-000 | §6, §8 | todo | Versão do Python fixada; dependências com versões exatas e lock; instalação travada documentada em §8 e funcionando em checkout limpo. Ferramenta de lock: Q-05 |
| T-003 | Propor portões de formatação e lint | T-000 | §8 | todo | Proposta apresentada ao humano (ferramenta, regras, custo); nada instalado sem aprovação (Q-05) |
| T-004 | Certificado A1: carregar PFX (`certificado.py`) | T-001, Q-03 | §7 | blocked (Q-03) | A definir com o humano |
| T-005 | Assinatura XMLDSIG (`assinatura.py`) | T-004, Q-06 | §5, §6 | todo | A definir; exige `[VERIFY]` do perfil de assinatura exigido pelo padrão nacional |
| T-006 | Codec GZip+Base64 (`codec.py`) | T-001 | §5 | todo | A definir; ida e volta sem perda |
| T-008 | Garantias de INV-02 e INV-03 | T-001 | §4, §7, §8 | todo | (1) `carregar_config()` sem variáveis de ambiente devolve `homologacao`; (2) `NFSE_AMBIENTE=producao` levanta erro claro citando DEC-002/INV-02; (3) portão novo em §8 que falha se `git ls-files` contiver `.env`, `*.pfx`, `*.p12` ou `*.pem`; (4) `.env.example` deixa de anunciar `producao` como opção |
| T-007 | Cliente mTLS e erros (`client.py`, `erros.py`) | T-004, T-005, T-006 | §6, §7 | todo | A definir; exige `[VERIFY]` de URLs e rotas; só produção restrita |

## §10 Registro de decisões

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

## §11 Perguntas em aberto

| ID | Pergunta | Bloqueia |
|---|---|---|
| Q-01 | **Respondida em 2026-10-07: os quatro aprovados, ver §4 e DEC-004.** Aprovar, ajustar ou rejeitar cada candidato a invariante de §4 (C-1 schemas oficiais intocados; C-2 default homologação; C-3 certificados e senhas fora do git; C-4 `Id` com 45 caracteres). Para C-2: basta o default, ou `producao` deve exigir uma confirmação explícita extra (ou ser recusado nesta fase, dado DEC-002)? | T-001, todas |
| Q-02 | O que fica congelado em §5: `schemas/1.01`? também `schemas/1.00` (não usado), ou removê-lo? As pastas vazias `schemas/Componente_Schemas` e `schemas/Componente_recepcao` (não rastreadas) têm algum uso? | T-001 |
| Q-03 | Certificado: `certs/lika-2026.pfx` já existe e o `.env` tem senha, mas o contexto dizia que ainda não há A1. É o certificado do cliente? Há autorização do titular para uso em homologação? Onde a DPS de teste pode ser emitida (CNPJ do titular)? Como tratar dados reais em `out/` e em logs? | T-004, T-007 |
| Q-04 | **Respondida em 2026-10-07: (a), ver DEC-003.** T-001, abordagem: (a) cópia gerada `schemas/1.01-local`, ignorada no git, com script e teste de diferença mínima (seu plano; recomendo, restringindo a remoção às âncoras de início/fim); (b) corrigir em memória ao carregar o esquema, sem arquivo derivado. Em (a), `scripts/preparar_xsd.py` (não rastreado) entra como base? E `.gitignore` ganha `schemas/*-local/`? | T-001 |
| Q-05 | Ferramentas a adicionar: lock (pip-tools, uv, `pip freeze` com hashes), formatador e linter (ex.: ruff), CI (GitHub Actions; há remoto `origin` no GitHub). | T-002, T-003 |
| Q-06 | Bibliotecas: nfelib só para bindings da DPS, ou manter o modelo próprio? Assinatura: signxml ou lxml+xmlsec? HTTP: httpx ou requests? | T-005, T-007 |
| Q-07 | Escopo e marcos: M1–M3 de §9 estão certos? Os passos 4 e 5 do README (decodificar retorno; consulta por chave e DANFSe) entram nesta fase? Critério de sucesso de M1 proposto: "G-1 e G-2 passam, com o teste de XSD rodando". | planejamento |
| Q-08 | Fronteiras de §3. Proposta: `src/dps.py` não depende de rede nem de certificado; só `client.py` faz I/O de rede; `scripts/` depende de `src/`, nunca o contrário. | T-004 em diante |
| Q-09 | Conflitos com o README: cita pydantic (contra DEC-001) e é um brainstorming, não uma descrição do projeto. Atualizar numa tarefa própria? | – |
| Q-10 | Licença: não há `LICENSE`. O remoto é `github.com/prbn021/nfse-poc`; se for público, o repositório redistribui os XSDs oficiais. Qual licença, e os XSDs podem ficar versionados? | cópia de código de terceiros |
| Q-11 | Formato de `serie` no XML ("1" ou "00001") e a quem reportar o defeito do padrão no XSD oficial (se quiser reportar). | T-001 (critério 1 independe) |
