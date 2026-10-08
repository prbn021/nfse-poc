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

Produto `[HUMAN]`: emissor de NFS-e via API NFS-e Nacional (padrão nacional, gov.br) para várias empresas, cada uma com o seu certificado A1 (DEC-024). Fase atual: PoC em Python no Windows (PowerShell, `.venv`), validada com o certificado de um primeiro emitente.

Perfil da carteira a atender `[HUMAN]`, respondido pelos contadores em 2026-10-08:

- Emitentes: só Simples Nacional ME/EPP. Nenhum MEI, Não Optante ou pessoa física. Sem regime especial, imunidade, isenção, benefício municipal ou dedução da base de cálculo.
- Raros casos de ISS recolhido por fora do Simples.
- Muitos municípios, todos emitindo pelo Emissor Nacional. Serviços diversos; há construção civil, serviço prestado em outro município e tomador no exterior.
- Tomadores pessoa física e jurídica, sempre identificados.
- Cerca de 100 notas por mês no total. Cancelamento e substituição são frequentes.
- Todo emitente tem certificado A1 válido; certificados e senhas ficam hoje com a equipe de contabilidade, que também informa o percentual de `pTotTribSN` de cada empresa, calculado sobre o faturamento e alterado com frequência.

Objetivo da fase `[HUMAN]`, em ordem:

1. Gerar a DPS em XML.
2. Validar offline contra os XSDs oficiais v1.01 (`schemas/1.01`).
3. Assinar (XMLDSIG).
4. GZip + Base64.
5. Transmitir via mTLS ao ambiente de produção restrita (homologação).

Dos dois passos que o brainstorming do `README.md` acrescenta, decodificar a NFS-e de retorno entra nesta fase, em M3; consultar por chave e baixar o DANFSe ficam para M4, fora dela (DEC-016).

Non-goals:

- Produção: nada toca produção `[HUMAN]` (DEC-002).
- Consulta por chave e DANFSe, cancelamento e substituição: M4, depois desta fase (DEC-016, DEC-024).
- Emitente MEI, Não Optante ou pessoa física: não há na carteira; o modelo os recusa com erro claro (DEC-024).
- ISS por fora do Simples (`regApTribSN` 2 ou 3): recusado por enquanto; T-023.
- API (FastAPI): só depois da PoC, segundo o `README.md`.

Critério de sucesso do milestone atual (M1): G-1 e G-2 passam, com T-010 e T-014 `done` (DEC-016).

## §2 Claims policy

O projeto hoje pode afirmar apenas:

| Claim | Evidence |
|---|---|
| Gera um XML de DPS a partir de dataclasses | `src/dps.py`, `tests/test_dps.py` (5 testes passam) |
| O XML de exemplo é válido contra uma cópia local do `DPS_v1.01.xsd` que difere do oficial em uma linha (âncoras do padrão de `serie`) | G-2; `tests/test_xsd.py` (DEC-003) |

Não pode afirmar: que emite NFS-e, que assina, que transmite, que é "válido contra o XSD oficial" sem ressalva, que o servidor aceita a DPS (a DPS de exemplo passa no XSD mas viola a regra E0712 do Anexo I e seria rejeitada; ver T-010), nem qualquer termo da lista do `CLAUDE.md` ("seguro", "pronto para produção" etc.). O `README.md` descreve o que existe e o que não existe nos mesmos termos desta seção (T-012); o brainstorming inicial ficou no fim dele, marcado como histórico.

## §3 Architecture

Existente:

```
scripts/gerar_dps.py ──> src/config.py  (lê .env via python-dotenv)
        │
        ├──────────────> src/dps.py     (dataclasses + lxml: modelo, para_xml, validar_xml)
        └──────────────> src/xsd.py     (cópia local dos XSDs sem âncoras)
scripts/preparar_xsd.py ─> src/config.py, src/xsd.py
scripts/checar_segredos.py ─> src/segredos.py  (lê `git ls-files`)
tests/ ────────────────> src/dps.py, src/xsd.py, src/config.py, src/segredos.py, docs/referencia/gov-docs (manifesto)
```

- `src/config.py`: `Config` imutável; `NFSE_AMBIENTE` tem default `homologacao` e `producao` levanta `ValueError` (INV-02); `tp_amb` 1=produção, 2=homologação.
- `src/segredos.py`: `proibidos` aponta, numa lista de caminhos, os que são `.env`, certificado (`.pfx`, `.p12`, `.pem`) ou arquivo de `docs/referencia/` fora de `gov-docs/`. `scripts/checar_segredos.py` aplica isso a `git ls-files` (G-4, INV-03, DEC-026).
- `src/dps.py`: `Prestador`, `Tomador`, `Servico`, `Valores`, `Dps`; `gerar_id`; `para_xml` (sem assinatura); `localizar_xsd_dps`; `validar_xml`.
- `src/xsd.py`: `remover_ancoras`, `dir_local`, `preparar_copia_local`. Gera `schemas/<versão>-local/` (ignorada no git) a partir dos oficiais, tirando só `^` inicial e `$` final dos `xs:pattern`; recusa escrever na pasta de origem (DEC-003).
- `scripts/preparar_xsd.py`: gera a cópia local sob demanda. `scripts/gerar_dps.py` a regenera a cada execução e valida contra ela.

Planejado no `README.md`, ainda inexistente: `certificado.py`, `assinatura.py`, `codec.py`, `client.py`, `erros.py`, `scripts/emitir.py`, `consultar.py`, `baixar_danfse.py`.

Boundaries de dependência, aprovadas pelo humano em 2026-10-08 (DEC-017):

- B-1: `src/dps.py` não depende de rede nem de certificado.
- B-2: só `src/client.py` faz I/O de rede.
- B-3: `scripts/` depende de `src/`; `src/` nunca depende de `scripts/`.

Exceções permitidas: nenhuma. O código atual respeita as três (não há módulo de rede nem de certificado). Ainda não há teste que as confira: T-016.

## §4 Invariants

Aprovados pelo humano em 2026-10-07 (DEC-004).

| ID | Statement | Enforced by |
|---|---|---|
| INV-01 | Os schemas oficiais em `schemas/1.01` nunca são editados | G-3 (`git diff --exit-code main -- schemas/1.01`) |
| INV-02 | O ambiente padrão é homologação, e `producao` é recusado pelo código enquanto durar a PoC | `test_sem_variaveis_o_ambiente_e_homologacao` e `test_producao_e_recusado` (`tests/test_config.py`), em G-1. A trava está em `carregar_config()`; ver o limite registrado na DEC-010 |
| INV-03 | Certificados e senhas nunca vão ao git | `.gitignore` (`.env`, `certs/`, `*.pfx`, `*.p12`, `*.pem`) e G-4, que falha se algum desses arquivos estiver rastreado |
| INV-04 | O `Id` da DPS é `DPS` + 42 dígitos (45 posições): município (7) + tipo de inscrição federal (1) + inscrição federal (14) + série (5) + número da DPS (15) | `test_id_tem_45_caracteres_e_composicao_correta` |
| INV-05 | Senha e conteúdo de certificado (chave privada, bytes do PFX) nunca aparecem em log, saída de terminal, `repr` ou mensagem de erro; os testes automatizados usam só dados fictícios e certificado autoassinado gerado por eles | Ainda sem teste: aprovado em 2026-10-08 (DEC-014), antes de existir código que abra certificado. A T-004 cria o teste, como acceptance criteria |
| INV-06 | Nada específico de um emitente fica fixo no código de `src/`: CNPJ, município, regime, códigos de serviço, percentuais e certificado são sempre dados de entrada | Ainda sem teste: aprovado em 2026-10-08 (DEC-024). A T-010 cria os testes, gerando a DPS para emitentes fictícios diferentes; a T-019 tira o certificado único da configuração |

## §5 Interfaces and frozen areas

Decididas pelo humano em 2026-10-07 (DEC-005).

Código e dados frozen (nunca editados):

- `schemas/1.01/` (INV-01), conferido por G-3.
- `docs/referencia/gov-docs/` (DEC-021, DEC-026): os 8 anexos e os 6 manuais oficiais. Conferido por `tests/test_gov_docs.py`, em G-1, contra o manifesto `SHA256SUMS` da pasta, e por G-3. Uma versão nova de um documento entra como arquivo novo, com o manifesto atualizado e uma DEC. `LEIAME.md` e `SHA256SUMS` são nossos e não são frozen.

Interfaces frozen (mudam só com nova versão, dados de teste regenerados e nova DEC):

- Formato do XML da DPS: layout v1.01, `versao="1.01"`, namespace `http://www.sped.fazenda.gov.br/nfse`, conforme `DPS_v1.01.xsd`.

Não frozen:

- Variáveis `NFSE_*` de `.env.example`: ainda devem mudar até a transmissão funcionar.
- `schemas/1.00/`: não era usado e foi removido do repositório em T-009 (2026-10-08).

Dados de teste "golden": não existem. `out/` é ignorado no git.

## §6 Dependencies and versions

| Item | Valor observado | Fixado? |
|---|---|---|
| Python | 3.11.9 (`.venv/pyvenv.cfg`) | Sim: `.python-version`. Um teste confere `3.11`; o patch não é conferido |
| lxml | 6.1.3 (libxml2 2.11.9, compilada e em execução) | Sim: `requirements.in`, lock em `requirements.txt` |
| python-dotenv | 1.2.4 | Sim: `requirements.in`, lock em `requirements.txt` |
| pytest | 9.1.1 | Sim: `requirements-dev.in`, lock em `requirements-dev.txt` |
| pip-tools | 7.6.2 | Sim: `requirements-dev.in`, lock em `requirements-dev.txt` |

- Dependências diretas com versão exata em `requirements.in` (execução) e `requirements-dev.in` (testes e pip-tools). Os locks `requirements.txt` e `requirements-dev.txt` são gerados pelo `pip-compile`, com versão exata e hashes SHA-256 de todas as dependências, inclusive `pip` e `setuptools`. Não são editados à mão (T-002, DEC-011).
- Os locks foram gerados no Windows com Python 3.11 e resolvem as dependências para essa plataforma (por exemplo, incluem `colorama`). Outra plataforma ou versão de Python exige gerar de novo.
- `pyvenv.cfg` registra que a venv foi criada em `C:\Users\preis\rpa\nfse-poc\.venv`, outro caminho. `python.exe -m …` funciona; os lançadores `.exe` em `.venv\Scripts` (ex.: `pytest.exe`) podem estar quebrados `[INFERRED]`. Os gates usam `python -m`.
- Bibliotecas escolhidas pelo humano em 2026-10-08 e ainda não instaladas (DEC-012, DEC-015): ruff (formatação e lint, T-003); signxml (assinatura, T-005), condicionada a `[VERIFY: perfil de assinatura XMLDSIG exigido pelo padrão nacional e se o signxml o produz]`; httpx (HTTP/mTLS, T-015 e T-007); `cryptography` (carregar o PFX e gerar o autoassinado dos testes, T-004). Cada uma entra, com versão exata e lock, na task que a usa. nfelib foi descartada: o modelo da DPS continua próprio. `[VERIFY: versões, licenças e API de ruff, signxml, httpx e cryptography, na task que instalar cada uma]`.

Itens de verificação:

| Item | Situação |
|---|---|
| Ordem e obrigatoriedade dos elementos da DPS | Parcial: o XML de exemplo valida sem erros contra o XSD v1.01 quando o padrão de `serie` é corrigido numa cópia (checado em 2026-10-07, diagnóstico de §8). Vale só para os elementos que o exemplo emite. Regras de negócio, parcial: o Anexo I (aba `RN DPS_NFS-e`) proíbe `indTotTrib` para emitente ME/EPP (E0712), e o código sempre o emite (checado em 2026-10-07; T-010). `[VERIFY: demais regras de negócio de obrigatoriedade do Anexo I, que o XSD não expressa; só foram lidas as dos campos que o exemplo emite]` |
| `opSimpNac` | 1 Não Optante; 2 MEI; 3 ME/EPP (checado em 2026-10-07, `tiposSimples_v1.01.xsd`, `TSOpSimpNac`) |
| `regEspTrib` | 0 Nenhum; 1 Ato Cooperado; 2 Estimativa; 3 Microempresa Municipal; 4 Notário ou Registrador; 5 Profissional Autônomo; 6 Sociedade de Profissionais; 9 Outros (checado em 2026-10-07, `TSRegEspTrib`) |
| `tribISSQN` | 1 Operação tributável; 2 Imunidade; 3 Exportação de serviço; 4 Não Incidência (checado em 2026-10-07, `TSTribISSQN`) |
| `tpRetISSQN` | 1 Não Retido; 2 Retido pelo Tomador; 3 Retido pelo Intermediário (checado em 2026-10-07, `TSTipoRetISSQN`) |
| Composição do `Id` | "DPS" + Cód.Mun (7) + Tipo de Inscrição Federal (1) + Inscrição Federal (14; CPF com 000 à esquerda) + Série (5) + Núm. DPS (15) = 45 (checado em 2026-10-07, `TSIdDPS`). Tipo de Inscrição Federal: 1 = CPF, 2 = CNPJ do emitente (checado em 2026-10-07, Anexo I v1.01, aba `LEIAUTE DPS_NFS-e`, campo `id`); o código fixa "2" e só aceita prestador com CNPJ |
| `totTrib` conforme `opSimpNac` | Não Optante (1): `indTotTrib` e `pTotTribSN` nunca podem ser informados. MEI (2): `pTotTribSN` nunca pode ser informado. ME/EPP (3): `indTotTrib` nunca pode ser informado (E0712). Sobra: Não Optante `vTotTrib` ou `pTotTrib`; MEI `vTotTrib`, `pTotTrib` ou `indTotTrib`; ME/EPP `vTotTrib`, `pTotTrib` ou `pTotTribSN` (checado em 2026-10-08, Anexo I v1.01, textos das regras; os códigos de rejeição das regras de Não Optante e MEI não foram anotados). O código hoje emite `indTotTrib` para todos (T-010). O emissor web oficial emitiu `pTotTribSN` numa NFS-e real de emitente ME/EPP (observado em 2026-10-08 no XML da nota de exemplo, em `docs/referencia/`, fora do git) |
| `regApTribSN` | Obrigatório quando `opSimpNac` = 3 e proibido quando é 1 ou 2 (checado em 2026-10-08, Anexo I v1.01; o XSD o declara opcional). Valores: 1 federais e municipal pelo SN; 2 federais pelo SN e ISSQN por fora; 3 federais e municipal por fora do SN (checado em 2026-10-08, `TSRegimeApuracaoSimpNac`). O modelo hoje não tem o campo (T-010). Posição no XML: `regTrib` traz `opSimpNac`, `regApTribSN`, `regEspTrib`, nessa ordem (observado em 2026-10-08 no XML da nota de exemplo) |
| Campos da DPS real que o modelo não gera | Além de `regApTribSN` e `pTotTribSN`: `cTribMun` em `cServ`; grupo `tribFed/piscofins` com `CST` e `tpRetPisCofins`; `fone` e `email` em `prest` (observado em 2026-10-08 no XML da nota de exemplo, emitida pelo emissor web). No Anexo I os quatro são opcionais, ocorrência 0-1; `CST` é obrigatório dentro de `piscofins`; se informados, `cTribMun` precisa existir e ser administrado pelo município de incidência (E0314) e `email` precisa ter estrutura de e-mail (E0148); `tribFed` é proibido para emitente pessoa física (E0675) (checado em 2026-10-08, abas `LEIAUTE DPS_NFS-e` e `RN DPS_NFS-e`, só as linhas desses campos). T-018 |
| Assinatura da NFS-e devolvida | `SignatureMethod` rsa-sha256; `DigestMethod` sha256; canonicalização `xml-exc-c14n#WithComments`; transformações `enveloped-signature` e `xml-exc-c14n#WithComments`; `KeyInfo` com `X509Certificate`; referência ao `Id` de `infNFSe` (observado em 2026-10-08 no XML da nota de exemplo). É a assinatura do sistema nacional sobre a NFS-e; a DPS embutida, do emissor web, não tem assinatura. Não fecha o `[VERIFY]` do perfil exigido da DPS assinada pelo contribuinte |
| URLs dos ambientes | Parcial: o host `adn.producaorestrita.nfse.gov.br` aparece no link do Swagger citado nos manuais dos contribuintes (checado em 2026-10-07; link não acessado). `[VERIFY: URL base da SEFIN em produção restrita e caminhos base das APIs]`. `.env.example` traz `https://sefin.producaorestrita.nfse.gov.br`, sem fonte. Rotas da SEFIN (`POST /nfse`, `GET /nfse/{chaveAcesso}`, `GET`/`HEAD /dps/{id}`): checadas em 2026-10-07, manual do Emissor Público |
| Procedência dos XSDs | `[VERIFY: que os arquivos em schemas/1.01 são o pacote oficial vigente, sem alterações]`. `schemas/LEIAME.md` aponta a página de origem, mas não há data de download nem hash publicado. A página lista hoje o pacote `NFSe-ESQUEMAS_XSD-v1.01-20260209` e declara o conteúdo do site sob CC BY-ND 3.0 (checado em 2026-10-08); o pacote não foi baixado nem comparado com `schemas/1.01` |
| Formato de `serie` no XML | `[VERIFY: se a série vai como "1" ou "00001"]`. O XSD aceita os dois; o `Id` usa 5 dígitos. O Anexo I só diz "numérico, tamanho 1-5" e não resolve; confirmar na primeira transmissão (Q-11). Indício, não prova: na nota de exemplo `nDPS` vai sem zeros à esquerda no elemento, embora ocupe 15 posições no `Id`; a série dela tem 5 dígitos e não resolve (observado em 2026-10-08) |
| Faixa de `serie` | 00001 a 49999 para aplicativo próprio; fora da faixa do emissor, rejeição E0010 (checado em 2026-10-07, Anexo I v1.01). O modelo hoje aceita 1 a 99999; restringir a 1–49999 é a T-014 (DEC-019) |

Todas as checagens "no XSD" valem para os arquivos locais, e dependem do item de procedência.

## §7 Security and secrets

- Segredos vêm de `.env` (ignorado no git) via `python-dotenv`: `NFSE_CERT_PATH`, `NFSE_CERT_PASSWORD`.
- `docs/referencia/` guarda arquivos com dados reais (notas de clientes) e é ignorada no git, exceto `gov-docs/`, que só tem documentação oficial. G-4 falha se algo dali fora de `gov-docs/` for rastreado (T-017).
- Ambientes: `homologacao` (default; "produção restrita") e `producao`. `carregar_config()` recusa `producao` com `ValueError` enquanto durar a PoC (INV-02, T-008).
- Nenhum segredo encontrado no histórico: `git ls-files` não contém `.env`, `.pfx`, `.p12` nem `.pem`.
- **Observação**: existe `certs/lika-2026.pfx` (8.719 bytes, ignorado no git) e o `.env` local tem `NFSE_CERT_PATH` apontando para ele e `NFSE_CERT_PASSWORD` preenchida. O contexto da conversa dizia que ainda não há certificado A1. Não abri o arquivo nem li a senha. O humano confirmou em 2026-10-07 que é o certificado do cliente (Q-03).
- Uso dos certificados (DEC-014): os testes automatizados usam sempre um certificado autoassinado gerado por eles. Um certificado real só é aberto por script manual: na T-004, para mostrar titular, CNPJ e validade; na T-015 e na T-007, para conectar em produção restrita. Hoje há um, o do primeiro emitente, cujo titular autorizou o uso em produção restrita `[HUMAN]`.
- Vários emitentes (DEC-024): cada emitente tem o seu certificado e a sua senha, hoje guardados pela equipe de contabilidade `[HUMAN]`. Na PoC ficam em arquivos locais fora do git, um conjunto por emitente (T-019); a configuração atual, com um único `NFSE_CERT_PATH` no `.env`, é provisória. Como o produto guarda certificados e senhas de terceiros, e quem autoriza o uso de cada um: Q-17.
- INV-05: senha e conteúdo de certificado nunca vão a log, terminal, `repr` ou mensagem de erro. Dados reais (CNPJ/CPF de tomadores, XML de DPS real) ficam só em arquivos fora do git (`out/`, `.env`, `docs/referencia/`); os testes usam dados fictícios.
- Repositório e licença (DEC-018): o repositório é público no GitHub (conferido em 2026-10-08) e não tem `LICENSE`, por decisão do humano: o código fica visível, sem permissão de uso para terceiros. Os XSDs em `schemas/1.01` são redistribuídos sem alteração, com crédito em `schemas/LEIAME.md`, sob a CC BY-ND 3.0 declarada na página de origem; a leitura de que o aviso do site cobre o pacote de schemas é do agente, não um parecer jurídico. Copiar código de terceiros para cá continua exigindo perguntar antes (não-negociável 8).
- Os dados de exemplo em `scripts/gerar_dps.py` e nos testes estão marcados como fictícios no código.

## §8 Gates

Comandos em PowerShell, a partir da raiz. Não há CI, Makefile nem scripts de verificação no repositório; os gates abaixo vêm do que o projeto já executa. Uma CI no GitHub Actions, em Windows, foi aprovada e entra na T-003 (DEC-012).

Preparação a partir de um checkout limpo, com instalação travada (G-5):

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --require-hashes -r requirements.txt -r requirements-dev.txt
Copy-Item .env.example .env
```

Para mudar uma dependência: editar o `.in`, gerar os dois locks de novo, nesta ordem, e reinstalar com o comando acima.

```powershell
.\.venv\Scripts\python.exe -m piptools compile --generate-hashes --strip-extras --allow-unsafe -o requirements.txt requirements.in
.\.venv\Scripts\python.exe -m piptools compile --generate-hashes --strip-extras --allow-unsafe -o requirements-dev.txt requirements-dev.in
```

| ID | Gate | Command | When |
|---|---|---|---|
| G-1 | Testes | `.\.venv\Scripts\python.exe -m pytest -q -rs` | Toda task |
| G-2 | Verificação do projeto: gerar e validar a DPS | `.\.venv\Scripts\python.exe scripts\gerar_dps.py` (sucesso = código de saída 0) | Toda task |
| G-3 | Áreas frozen intocadas (XSDs e documentação oficial) | `git diff --exit-code main -- schemas/1.01 docs/referencia/gov-docs` | Toda task |
| G-4 | Nenhum segredo ou referência privada rastreados (`.env`, `*.pfx`, `*.p12`, `*.pem`, e `docs/referencia/` fora de `gov-docs/`) | `.\.venv\Scripts\python.exe scripts\checar_segredos.py` (sucesso = código de saída 0) | Toda task |
| – | Formatação | inexistente | ruff, a implementar em T-003 (DEC-012) |
| – | Lint com avisos como erro | inexistente | ruff, a implementar em T-003 (DEC-012) |
| G-5 | Instalação travada | `.\.venv\Scripts\python.exe -m pip install --require-hashes -r requirements.txt -r requirements-dev.txt` (precisa de rede) | Ao preparar o ambiente e em toda task que mude um `requirements*`. Nas demais, `tests/test_lock.py` (em G-1) confere que o ambiente bate com os locks |
| – | Build | não se aplica: o projeto não gera pacote nem binário | – |

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
- G-2: código de saída 0, `[OK] Válida contra DPS_v1.01.xsd (cópia local em …\schemas\1.01-local)`. Também sai com 0 sem `.env` (executado), porque o default de `NFSE_XSD_DIR` passou a ser `schemas/1.01`.
- G-3: sem diferenças.

### Fechamento da T-001 (2026-10-07, mesma branch)

Reexecutados antes e depois de atualizar o spec e as fontes com a documentação de `docs/referencia/`, com o mesmo resultado: G-1 `26 passed`, nenhum pulado; G-2 código de saída 0, `[OK] Válida contra DPS_v1.01.xsd`; G-3 sem diferenças.

### Depois de T-008 (2026-10-07, branch `t-008-production-lock-and-secrets-gate`)

- G-1: `44 passed`, nenhum pulado (18 testes novos em `tests/test_config.py` e `tests/test_segredos.py`).
- G-2: código de saída 0. Com `NFSE_AMBIENTE=producao`, sai com código 1 e `ValueError` citando INV-02 e DEC-002 (executado).
- G-3: sem diferenças.
- G-4 (novo): código de saída 0, nenhum `.env` ou certificado entre os arquivos rastreados.

### Depois de T-002 (2026-10-07, branch `t-002-pin-toolchain-and-deps`)

- G-5 (novo): código de saída 0 no `.venv` do projeto e num clone novo da branch, em diretório temporário, com `py -3.11 -m venv`.
- No clone novo, sem `.env`: G-1 `51 passed`; G-2 código de saída 0; G-4 código de saída 0. G-3 não foi rodado no clone.
- No repositório: G-1 `51 passed`, nenhum pulado (7 testes novos em `tests/test_lock.py`); G-2 código 0; G-3 sem diferenças; G-4 código 0.
- As versões resolvidas pelo lock são as mesmas que já estavam instaladas antes da task; a instalação travada acrescentou ao `.venv` o pip-tools e as dependências dele, e atualizou o `pip` para a versão do lock.

### Depois de T-009 (2026-10-08, branch `t-009-remove-schemas-1-00`)

- G-3 passou a conferir só `schemas/1.01` (DEC-005, critério 2 da T-009): sem diferenças. Com o comando antigo ele acusaria a remoção de `schemas/1.00`, que é o objetivo da task.
- G-1: `52 passed`, nenhum pulado (1 teste novo: só a versão 1.01 existe em `schemas/`). G-2: código de saída 0. G-4: código de saída 0.

### Depois de T-012 (2026-10-08, branch `t-012-readme-setup-and-test`)

- Só `README.md` e `docs/SPEC.md` mudaram. G-1: `52 passed`, nenhum pulado. G-2: código de saída 0. G-3: sem diferenças. G-4: código de saída 0.
- Os comandos de preparação do README foram executados no `.venv` do projeto, recriado pelo humano com `py -3.11 -m venv` nesta data: G-5 código de saída 0. Não foram repetidos num clone novo.

### Depois de T-013 (2026-10-08, branch `t-013-answer-open-questions`)

- Só `docs/SPEC.md`, `docs/SOURCES.md` e `schemas/LEIAME.md` mudaram. G-1: `52 passed`, nenhum pulado. G-2: código de saída 0. G-3: sem diferenças. G-4: código de saída 0.

### Depois de T-017 (2026-10-08, branch `t-017-version-official-docs`)

- G-1: `64 passed`, nenhum pulado (12 testes novos: 8 casos em `tests/test_segredos.py` e 4 em `tests/test_gov_docs.py`). G-2: código de saída 0. G-4: código de saída 0, com 54 arquivos rastreados.
- G-3 com o comando novo acusa, nesta branch, os 16 arquivos acrescentados em `docs/referencia/gov-docs/`, que é o objetivo da task; depois do merge volta a passar. Para `schemas/1.01`, sem diferenças.
- G-4 testado à mão: com uma cópia da nota de exemplo adicionada ao índice do git, sai com código 1 e aponta o arquivo; desfeito em seguida.

### Diagnóstico da falha de G-2 (hipótese confirmada)

1. **Norma.** XML Schema Part 2, Apêndice F: as expressões regulares são ancoradas implicitamente no início e no fim; `^` e `$` não são metacaracteres (`^` só tem papel especial dentro de `[...]`). Num `xs:pattern`, portanto, são caracteres literais.
2. **Comportamento do libxml2 2.11.9 (via lxml 6.1.3).** Esquema mínimo com o mesmo padrão: `^0{0,4}\d{1,5}$` rejeita `1` e `00001` e aceita os textos literais `^1$` e `^00001$`. Sem as âncoras, aceita `1` e `00001` e rejeita `^1$` e `abc`.
3. **Alcance.** Dos 54 `xs:pattern` em `schemas/1.01`, só um tem âncoras: `TSSerieDPS`, `tiposSimples_v1.01.xsd` linha 161. Em `schemas/1.00` não havia nenhum (pasta removida em T-009).
4. **Efeito da correção.** Com uma cópia dos XSDs fora do repositório, trocando só esse padrão por `0{0,4}\d{1,5}`, a DPS de exemplo valida com 0 erros. Não há outra falha escondida atrás desta para o XML de exemplo.

Consequência: nenhum valor de `serie` que a API aceitaria passa no XSD oficial com um validador conforme a norma. O validador do servidor provavelmente usa um motor que trata `^`/`$` como âncoras `[INFERRED]`; validar offline contra uma cópia corrigida não prova que o servidor aceita.

## §9 Milestones and tasks

Milestones confirmados pelo humano em 2026-10-08 (DEC-016). Milestone atual: M1.

- **M1**: DPS gerada e válida offline contra o XSD v1.01. Sucesso: G-1 e G-2 passam, com T-010 e T-014 `done`. T-018 também é trabalho de M1, mas não entra no critério de sucesso aprovado.
- **M2**: DPS assinada e empacotada (XMLDSIG, GZip+Base64): T-004, T-005, T-006.
- **M3**: transmissão via mTLS em produção restrita, com a NFS-e de retorno decodificada: T-015, T-007.
- **M4** (fora desta fase): cancelamento e substituição de NFS-e; consulta por chave e download do DANFSe. Sem tasks ainda; a ordem entre eles se decide quando o M3 fechar.
- Fora dos milestones, depois da primeira transmissão: T-020 a T-023, que ampliam o modelo para os casos da carteira.

Phase gates: toda PR é um phase gate (decisão do humano em 2026-10-07). Cada task para em `review` e só vai a `done` depois da revisão do humano.

| ID    | Title | Deps | Reads | Status | Acceptance criteria |
|-------|--------|------|-------|--------|------------------------|
| T-000 | Bootstrap: spec, fontes e baseline | – | CLAUDE.md | done | `docs/SPEC.md` e `docs/SOURCES.md` no branch `t-000-spec`; baseline de G-1 e G-2 registrado; humano escreve `Approved:` em §0 |
| T-001 | Validação offline da DPS falha no padrão de `serie` | T-000, Q-01, Q-04 | §4, §5, §6, §8 | done | (1) G-2 sai com código 0 e imprime `[OK] Válida`; (2) `test_xml_valido_contra_xsd_oficial` deixa de ser pulado e passa; (3) `git diff main -- schemas/1.00 schemas/1.01` vazio; (4) teste negativo: `serie` inválida (ex.: `abc`, 6 dígitos) continua rejeitada pelo esquema usado na validação; (5) se houver cópia derivada: é regenerável por script, ignorada no git, e um teste garante que ela difere dos oficiais só nas âncoras `^`/`$` de início e fim de `xs:pattern` (hoje, 1 linha); (6) `.env.example` e o default de `NFSE_XSD_DIR` coerentes com o local real dos XSDs |
| T-002 | Fixar toolchain e dependências | T-000 | §6, §8 | done | Versão do Python fixada; dependências com versões exatas e lock; instalação travada documentada em §8 e funcionando em checkout limpo. Ferramenta de lock: pip-tools (Q-05, DEC-011) |
| T-003 | Gates de formatação e lint com ruff, e CI em Windows | T-000 | §6, §8 | todo | (1) as regras do ruff são apresentadas ao humano e aprovadas antes de qualquer instalação; (2) ruff com versão exata em `requirements-dev.in` e nos locks; (3) dois gates novos em §8, formatação e lint com avisos como erro, passando no código existente; (4) workflow do GitHub Actions em `windows-latest` que faz a instalação travada (G-5) e roda os gates em toda PR; (5) nenhuma mudança de comportamento: G-1 e G-2 com o mesmo resultado (DEC-012) |
| T-004 | Certificado A1: carregar PFX (`certificado.py`) | T-001, T-019 | §3, §4, §7 | todo | (1) carrega um PFX com senha e expõe certificado e chave privada; (2) os testes usam um PFX autoassinado gerado por eles, nunca o do cliente; (3) senha errada, arquivo ausente e arquivo que não é PFX geram erro claro; (4) teste de INV-05: a senha e a chave não aparecem em `repr`, em mensagem de erro nem em log; (5) `certificado.py` recebe caminho e senha como argumentos, sem certificado global; um script manual abre o certificado do emitente indicado e mostra só titular, CNPJ e validade; (6) `cryptography` com versão exata e lock; (7) B-1 a B-3 respeitadas (DEC-014) |
| T-005 | Assinatura XMLDSIG (`assinatura.py`) | T-004 | §5, §6 | todo | A definir com o humano depois de fechar o `[VERIFY]` do perfil de assinatura do padrão nacional (§6). Já decidido: signxml, se atender ao perfil; se não atender, voltar ao humano (DEC-015). Testes só com certificado autoassinado |
| T-006 | Codec GZip+Base64 (`codec.py`) | T-001 | §5 | todo | (1) codificar: XML em bytes → GZip → Base64 em texto; (2) decodificar faz o inverso e devolve os mesmos bytes, com teste de ida e volta sobre entradas variadas; (3) entrada que não é Base64 ou GZip válido gera erro claro; (4) a saída é lida pelo `gzip` da biblioteca padrão; (5) só biblioteca padrão, sem dependência nova. Aprovados pelo humano em 2026-10-08 |
| T-008 | Garantias de INV-02 e INV-03 | T-001 | §4, §7, §8 | done | (1) `carregar_config()` sem variáveis de ambiente devolve `homologacao`; (2) `NFSE_AMBIENTE=producao` levanta erro claro citando DEC-002/INV-02; (3) gate novo em §8 que falha se `git ls-files` contiver `.env`, `*.pfx`, `*.p12` ou `*.pem`; (4) `.env.example` deixa de anunciar `producao` como opção |
| T-009 | Remover `schemas/1.00` do repositório | T-001 | §5, §8 | done | (1) `schemas/1.00/` removido do git; (2) G-3 passa a conferir só `schemas/1.01`; (3) `schemas/LEIAME.md` e `docs/SOURCES.md` coerentes com a remoção; (4) G-1 e G-2 continuam passando |
| T-010 | `totTrib` e `regApTribSN` conforme o Simples Nacional | T-001 | §5, §6 | todo | (1) com `op_simp_nac=3` o XML não contém `indTotTrib`, emite `pTotTribSN` e emite `regApTribSN`, que passa a ser campo obrigatório do modelo para ME/EPP; (2) `regApTribSN` é recusado pelo modelo quando `op_simp_nac` é 1 ou 2; (3) `pTotTribSN` é recusado para Não Optante e MEI, e `indTotTrib` para Não Optante e ME/EPP; (4) o exemplo de `scripts/gerar_dps.py` usa o perfil mais comum da carteira (ME/EPP, tomador pessoa física, prestador sem inscrição municipal), com dados fictícios; (5) os XMLs gerados são válidos contra a cópia local dos XSDs; (6) o modelo recusa com erro claro de "ainda não suportado", em vez de gerar um XML que o servidor rejeitaria: `op_simp_nac` 1 (Não Optante) e 2 (MEI), e `regApTribSN` 2 e 3 (ISS por fora, T-023); (7) testes de INV-06: a DPS é gerada e validada para pelo menos dois emitentes fictícios de municípios e serviços diferentes, com tomador CPF e com tomador CNPJ, e nenhum default de `src/` carrega dado de emitente (DEC-013, DEC-022, DEC-024) |
| T-007 | Cliente mTLS e erros (`client.py`, `erros.py`) | T-004, T-005, T-006, T-010, T-015 | §3, §6, §7 | todo | A definir; inclui decodificar a NFS-e de retorno (DEC-016); httpx (DEC-015); o ambiente vem só de `Config` (DEC-010); exige `[VERIFY]` de URLs e rotas; só produção restrita |
| T-011 | Termos do `CLAUDE.md` em inglês e regras básicas do projeto | T-001 | CLAUDE.md, §0, §9, §10 | done | (1) títulos de seção, colunas e termos do spec em inglês, conforme DEC-006; (2) §0 com as regras de idioma, de `Approved`/`done` e de PR e merge; (3) DEC-006 a DEC-009 registradas; (4) nenhum arquivo fora de `docs/` alterado; (5) G-1 a G-3 passam |
| T-012 | README: como preparar, rodar e testar | T-002, T-009 | §2, §8 | done | (1) o `README.md` traz os comandos de preparação (instalação travada, G-5), execução e teste, iguais aos de §8; (2) cobre os erros que o humano encontrou em 2026-10-08 (`No module named pytest` por instalar só o `requirements.txt`; caminho de script incompleto); (3) nenhum claim além dos de §2; (4) o brainstorming anterior é mantido, marcado como histórico; (5) só `README.md` e `docs/` mudam; (6) G-1 a G-4 passam |
| T-013 | Responder as open questions | T-012 | §11 | done | (1) cada resposta do humano de 2026-10-08 transcrita em §11 e registrada como DEC; (2) as seções afetadas do spec (§1, §3, §4, §6, §7, §8, §9) coerentes com as respostas; (3) fatos novos checados em `docs/SOURCES.md`; (4) `schemas/LEIAME.md` cita a licença e o nome do pacote de origem; (5) nenhum código alterado; (6) G-1 a G-4 passam |
| T-014 | Restringir `serie` a 1–49999 no modelo | T-001 | §4, §6 | todo | (1) `Dps` recusa `serie` fora de 1–49999 com erro claro que cita a faixa do aplicativo próprio; (2) testes nos limites: 1 e 49999 aceitos, 0 e 50000 recusados; (3) o XML do exemplo continua válido (DEC-019) |
| T-015 | Teste de conexão mTLS em produção restrita | T-004 | §6, §7 | todo | (1) `[VERIFY]` da URL base da SEFIN em produção restrita fechado antes de qualquer chamada; (2) um script manual abre uma conexão mTLS com o certificado do emitente indicado e faz uma consulta que não emite nem altera nada (qual rota: a confirmar com o humano na task); (3) o resultado (status HTTP, erro de TLS ou sucesso) é registrado no spec; (4) nada de senha, chave ou conteúdo do certificado na saída (INV-05); (5) recusa qualquer ambiente que não seja produção restrita (INV-02); (6) httpx com versão exata e lock; (7) sem teste automatizado que dependa de rede ou do certificado real (DEC-014) |
| T-016 | Teste das boundaries de §3 | T-001 | §3 | todo | (1) um teste em G-1 lê os imports de `src/` e falha se `src/dps.py` importar módulo de rede ou de certificado, se outro módulo que não `src/client.py` importar biblioteca de rede, ou se `src/` importar de `scripts/`; (2) teste negativo com um módulo de exemplo que viola cada regra; (3) passa no código atual (DEC-017) |
| T-017 | Versionar a documentação oficial em `docs/referencia/gov-docs/` | T-013 | §5, §7, §8 | review | (1) os 8 anexos e os 6 manuais oficiais ficam em `docs/referencia/gov-docs/`, rastreados e sem alteração, com o SHA-256 de cada um em `docs/SOURCES.md`; (2) o `.gitignore` continua ignorando o resto de `docs/referencia/`; (3) a nota fiscal do cliente e qualquer arquivo com dado real continuam fora do git, e um gate falha se algo de `docs/referencia/` fora de `gov-docs/` estiver rastreado; (4) `LEIAME.md` na pasta com a página de origem, a data e a licença; (5) a pasta entra em §5 como frozen, conferida por gate; (6) os caminhos citados em `docs/SOURCES.md` batem com os arquivos; (7) G-1 a G-4 passam (DEC-021) |
| T-018 | Campos opcionais da DPS usados nas notas atuais | T-010 | §5, §6 | todo | (1) o modelo aceita, todos opcionais: `cTribMun` (3 dígitos) no serviço; `fone` e `email` no prestador; grupo `tribFed/piscofins` com `CST` (obrigatório dentro do grupo) e `tpRetPisCofins`; (2) sem esses campos o XML sai igual ao de hoje; (3) cada um na posição do XSD, e os XMLs válidos contra a cópia local; (4) testes negativos: `cTribMun` fora de 3 dígitos, `email` sem estrutura de e-mail (E0148), `CST` e `tpRetPisCofins` fora das tabelas; (5) o exemplo de `scripts/gerar_dps.py` passa a emitir os quatro, com dados fictícios; (6) fora do escopo: base de cálculo, alíquotas e valores de PIS/COFINS e as demais retenções federais (DEC-023) |
| T-019 | Configuração por emitente (lista de certificados) | T-001 | §3, §4, §7 | todo | (1) o `.env` fica só com o que é do ambiente (`NFSE_AMBIENTE`, URLs, `NFSE_XSD_DIR`); `NFSE_CERT_PATH` e `NFSE_CERT_PASSWORD` saem de `Config`; (2) cada emitente tem um arquivo local, numa pasta ignorada no git, com caminho do certificado, senha e dados fixos do emitente (CNPJ, município, inscrição municipal, regime); (3) um arquivo de exemplo com dados fictícios é versionado, e os scripts recebem qual emitente usar; (4) emitente inexistente ou arquivo incompleto gera erro claro; (5) a senha não aparece em `repr` nem em mensagem de erro (INV-05); (6) G-4 passa a recusar arquivos de emitente rastreados, exceto o de exemplo; (7) só biblioteca padrão para ler o arquivo; (8) o que muda a cada nota (tomador, serviço, valores, percentual de `pTotTribSN`) não fica no arquivo do emitente (DEC-024) |
| T-020 | Construção civil: grupo de obra na DPS | T-018 | §5, §6 | todo | A definir depois de ler no Anexo I as regras do grupo de obra. Existe na carteira (DEC-024) |
| T-021 | Serviço prestado em outro município | T-018 | §5, §6 | todo | A definir depois de ler no Anexo I as regras de local de incidência e de retenção do ISSQN quando o local da prestação difere do município do emitente. Existe na carteira (DEC-024) |
| T-022 | Tomador no exterior | T-018 | §5, §6 | todo | A definir depois de ler no Anexo I as regras de tomador com NIF e endereço no exterior e do grupo de comércio exterior. Existe na carteira (DEC-024) |
| T-023 | ISS por fora do Simples (`regApTribSN` 2 e 3) | T-010 | §5, §6 | todo | A definir depois de ler no Anexo I as regras desses regimes de apuração (alíquota, retenção). Casos raros na carteira; até lá o modelo recusa (DEC-024) |

### Ponto de retomada (2026-10-08)

Estado ao fim da sessão de 2026-10-08. Para retomar com o agente: pedir que leia o `CLAUDE.md` e este ponto de retomada.

**Onde o trabalho parou**

- `main` está em `422aec0` e contém T-000, T-001, T-002, T-008, T-009, T-011, T-012 e T-013, todas `done`. T-013 entrou pela PR #7 e foi marcada `done` pelo humano na conversa de 2026-10-08 (transcrito pelo agente, DEC-007).
- T-017 (versionar a documentação oficial) está em `review` na branch `t-017-version-official-docs`. Falta o humano abrir a PR, mesclar com squash e pedir o `done`:
  - link: `https://github.com/prbn021/nfse-poc/compare/main...t-017-version-official-docs?expand=1`
  - título: `T-017: version the official documentation under docs/referencia/gov-docs`

**Para preparar uma máquina**

1. Seguir "Preparar o ambiente" do `README.md` (instalação travada, G-5) e rodar G-1 a G-4.
2. Não viajam pelo git e precisam ser levados à mão, se forem necessários: `certs/*.pfx` e a senha, o que está em `docs/referencia/` fora de `gov-docs/` (a nota de exemplo, que tem dados reais), chave SSH, `git config user.name`/`user.email`. `schemas/1.01-local` é regenerada por `scripts/gerar_dps.py`.
3. Se a máquina não tiver o `gh`, as PRs são abertas pela interface do GitHub, com link, título e descrição entregues pelo agente.

**Próxima task e o que está pendente para ela**

- Ordem das próximas (DEC-020 e DEC-025, confirmadas pelo humano em 2026-10-08): T-003, T-016, T-019, T-004, T-015, T-010, T-014, T-018, T-006, T-005, T-007, e depois T-020 a T-023. A ideia: depois das duas tasks de preparação, ir direto ao certificado e ao teste de conexão mTLS, que é o maior risco e pode depender de terceiros; o trabalho no modelo (M1) vem em seguida.
- **T-003** está liberada: ruff e CI em Windows aprovados (DEC-012). Ela começa apresentando as regras do ruff, antes de instalar.
- **T-010** está liberada (DEC-013, DEC-022, DEC-024): só ME/EPP com tudo pelo Simples; Não Optante, MEI e ISS por fora são recusados pelo modelo.
- **T-020 a T-023** têm acceptance criteria "a definir": dependem de ler as regras do Anexo I para cada caso.
- **T-005** e **T-007** ainda têm acceptance criteria "a definir".
- Open questions sem resposta: Q-17 (guarda de certificados e senhas no produto) e Q-18 (como o percentual mensal de `pTotTribSN` entra no sistema). Nenhuma bloqueia a PoC. Parcial: Q-11 (formato de `serie`, a confirmar na primeira transmissão).
- `[VERIFY]` abertos em §6: formato de `serie` no XML, URL base da SEFIN, procedência dos XSDs, demais regras de negócio do Anexo I, perfil de assinatura XMLDSIG, versões e licenças das bibliotecas escolhidas.

**Outros**

- As branches já mescladas (`t-002-…`, `t-008-…`, `t-009-…`, `t-011-…`, `t-012-…`) continuam em `origin` por escolha do humano.
- Regras de trabalho em §0: commits, PRs e branches em inglês; uma PR por task com squash; `done` só a pedido explícito.

### Histórico do ponto de retomada (2026-10-07 e 2026-10-08)

Registro das atualizações anteriores, em ordem. O estado atual é o da seção acima.

- T-000 e T-001 em `review`, aguardando o humano marcar `done`. Branches `t-000-spec` e `t-001-validacao-serie-xsd` publicadas em `origin`; `main` só tem o commit inicial.
- §11 respondidas: Q-01, Q-02, Q-04. Parcial: Q-03. Ainda não discutidas: Q-05 a Q-11, nessa ordem.
- Tasks criadas e não iniciadas: T-008 (trava de `producao` e gate de segredos), T-009 (remover `schemas/1.00`).
- O humano já tem, fora do repositório: a documentação oficial (PDFs e planilhas) e uma nota fiscal antiga do cliente. Destino combinado: documentação em `docs/referencia/` (ignorada no git); nota fiscal em `certs/` ou `out/` (ignoradas), por conter dados reais. Com elas dá para fechar os `[VERIFY]` de §6 e montar os dados reais do prestador, que ficam em arquivo local fora do git, nunca no código nem nos testes.
- Atualização no fechamento da T-001 (2026-10-07): a documentação oficial e a nota de exemplo já estão em `docs/referencia/` (ignorada no git). Com ela foram fechados o Tipo de Inscrição Federal do `Id` e a faixa de `serie`, e registradas as rotas da SEFIN e as regras de recepção (§6, `docs/SOURCES.md`). Seguem abertos: formato de `serie` no XML, URL base da SEFIN, procedência dos XSDs. Lacuna nova: E0712 (T-010). Open questions novas: Q-12 e Q-13. Os dados reais do prestador ainda não foram montados em arquivo local.
- T-000 e T-001 marcadas `done` pelo humano na conversa de 2026-10-07 (status transcrito pelo agente a pedido dele). As branches ainda não foram mescladas em `main`.
- Atualização em T-011 (2026-10-07): T-000 e T-001 entraram em `main` pela PR #1, com squash, no commit `65c2e9b`. As branches `t-000-spec` e `t-001-validacao-serie-xsd` ficaram obsoletas. Próxima task pela ordem da DEC-009: T-008. Open questions sem resposta: Q-05 a Q-10, Q-12 e Q-13; parciais: Q-03 e Q-11.
- T-011 entrou em `main` pela PR #2 (`b9c6e52`) e foi marcada `done` pelo humano na conversa de 2026-10-07 (transcrito pelo agente, DEC-007).
- T-008 em `review` na branch `t-008-production-lock-and-secrets-gate`. Próxima pela DEC-009: T-002, que depende de Q-05; se Q-05 seguir aberta, T-009.
- T-008 entrou em `main` pela PR #3 (`a7e58dd`); continua em `review` no quadro até o humano pedir o `done`. T-002 em `review` na branch `t-002-pin-toolchain-and-deps`. Na outra máquina, recriar o `.venv` com a instalação travada de §8. Próxima pela DEC-009: T-009.
- 2026-10-08: T-008 marcada `done` pelo humano na conversa (transcrito pelo agente, DEC-007). T-002 entrou em `main` pela PR #4 (`427d47c`) e continua em `review` no quadro até o humano pedir o `done`.
- T-009 em `review` na branch `t-009-remove-schemas-1-00`. Próxima pela DEC-009: T-003 (proposta de formatação, lint e CI), que precisa do resto de Q-05.
- Não viajam pelo git e precisam ser recriados na outra máquina: `.venv`, `.env` (copiar de `.env.example`), `certs/*.pfx` e a senha, chave SSH, `git config user.name`/`user.email`, `docs/referencia/`. `schemas/1.01-local` é regenerada por `scripts/gerar_dps.py`.
- 2026-10-08: T-009 entrou em `main` pela PR #5 (`88af46e`) e foi marcada `done` pelo humano (transcrito pelo agente, DEC-007). T-012 criada a pedido do humano, depois de ele instalar só o `requirements.txt` e ficar sem o pytest; feita em branch própria depois do merge da T-009, por escolha dele.
- 2026-10-08: T-012 entrou em `main` pela PR #6 (`d84d291`) e foi marcada `done` pelo humano (transcrito pelo agente, DEC-007). T-013 criada a pedido do humano para responder as open questions; respondidas nesta data: Q-03, Q-05, Q-06, Q-07, Q-08, Q-09, Q-10, Q-12 e Q-13, mais os acceptance criteria da T-006. Tasks novas: T-014, T-015, T-016, T-017 (versionar a documentação oficial, DEC-021) e T-018 (campos opcionais usados pelo cliente, DEC-023). Open questions novas: Q-14, Q-15 e Q-16 (respondidas na mesma data), Q-17 e Q-18. O humano informou que o produto atende várias empresas e trouxe respostas dos contadores sobre o perfil da carteira (DEC-024); tasks novas T-019 a T-023. O humano autorizou o agente a ler a nota fiscal antiga do cliente (PDF e XML, em `docs/referencia/`, fora do git); nenhum dado dela foi escrito no repositório.
- 2026-10-08: T-013 entrou em `main` pela PR #7 (`422aec0`) e foi marcada `done` pelo humano (transcrito pelo agente, DEC-007). T-017 em `review` na branch `t-017-version-official-docs`. Próxima pela ordem: T-003.

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

### DEC-010: Trava de `producao` em `carregar_config()` e G-4 como script (2026-10-07, T-008)
Context: INV-02 e INV-03 estavam aprovados sem garantia em código. Os acceptance criteria da T-008 pedem a recusa de `NFSE_AMBIENTE=producao` e um gate que falhe se o git rastrear `.env` ou certificado.
Decision: do agente (escolhas de implementação): a recusa fica em `carregar_config()`, antes da checagem de valor desconhecido, com mensagem que cita INV-02 e DEC-002. O gate é `scripts/checar_segredos.py`, casca fina sobre `src/segredos.py` (mesmo desenho de `preparar_xsd.py` sobre `src/xsd.py`), para a regra ser testável sem depender do git. Casa `.env` pelo nome exato do arquivo e as extensões sem diferenciar maiúsculas; `.env.example` passa.
Alternatives: um comando `git ls-files` direto em §8 (rejeitado: sintaxe diferente em PowerShell e bash, e sem teste); um hook de pre-commit (rejeitado: seria ferramenta nova, item de "perguntar"); remover `producao` de `TP_AMB` (rejeitado: o mapeamento 1 = produção é um fato do leiaute, e a mensagem de erro específica é mais clara).
Consequences: §3, §4, §7, §8. Limite: a trava cobre o caminho de configuração. `Dps(tp_amb=1)` ainda pode ser construída por chamada direta, porque o modelo aceita os dois valores do leiaute; nada transmite hoje, e a T-007 deve obter o ambiente só de `Config`. G-4 olha os arquivos rastreados agora, não o histórico de commits.

### DEC-011: Lock de dependências com pip-tools (2026-10-07, T-002)
Context: `requirements.txt` listava três pacotes sem versão e não havia versão de Python fixada, o que descumpria o não-negociável 10 do `CLAUDE.md`. Q-05 perguntava a ferramenta de lock.
Decision: do humano, na conversa de 2026-10-07: pip-tools. Escolhas de implementação do agente: `.python-version` com `3.11.9`; dois pares entrada/lock, `requirements.in` → `requirements.txt` (execução) e `requirements-dev.in` → `requirements-dev.txt` (pytest e o próprio pip-tools, restrito por `-c requirements.txt`); versões exatas já nos `.in`, iguais às que estavam instaladas, para a task não mudar comportamento; locks com `--generate-hashes` e `--allow-unsafe`, para `pip` e `setuptools` também terem hash e a instalação com `--require-hashes` funcionar; `tests/test_lock.py` confere em G-1 que os locks têm versão exata e hash e que o ambiente em uso bate com eles.
Alternatives: uv (rejeitado pelo humano: troca o fluxo de venv e pip); `pip freeze` (rejeitado: sem hashes e sem separar dependências diretas); um único lock para tudo (rejeitado: misturaria pytest e pip-tools com o que a execução precisa).
Consequences: §6, §8 (G-5), §9, §11. Os locks valem para Windows com Python 3.11; uma CI em Linux (T-003) exige gerar um lock para essa plataforma. O teste do Python confere só `3.11`, não o patch. `requirements.txt` deixou de ser editável à mão.

### DEC-012: ruff e CI no GitHub Actions em Windows (2026-10-08, T-013)
Context: Q-05 seguia aberta para o formatador, o linter e a CI; a T-003 era só uma proposta.
Decision: do humano, na conversa de 2026-10-08: ruff como formatador e linter; CI no GitHub Actions em runner Windows.
Alternatives: black + flake8 (rejeitado: duas ferramentas para o mesmo resultado); sem formatação e lint por enquanto; CI em Linux (rejeitado: exigiria gerar e manter um segundo par de locks, DEC-011); sem CI.
Consequences: §6, §8, §9. A T-003 passa de proposta a implementação, mas ainda apresenta as regras do ruff antes de instalar. A CI usa os locks atuais sem mudança.

### DEC-013: `pTotTribSN` e `regApTribSN` para ME/EPP; exemplo com o perfil do cliente (2026-10-08, T-013)
Context: Q-13. O Anexo I proíbe `indTotTrib` para ME/EPP (E0712) e, checado nesta data, também para Não Optante; torna `regApTribSN` obrigatório para ME/EPP. O código emite `indTotTrib` para todos e não tem `regApTribSN`.
Decision: do humano, na conversa de 2026-10-08: (a) ME/EPP emite `pTotTribSN`; (c) o exemplo e os testes espelham o perfil do cliente (ME/EPP, tomador pessoa física, prestador sem inscrição municipal), sempre com dados fictícios. (b) foi respondida pela documentação, não por escolha: `regApTribSN` é obrigatório para ME/EPP e entra no modelo.
Alternatives: `pTotTrib` ou `vTotTrib` para ME/EPP (rejeitados: três valores onde um basta); manter o exemplo atual, com tomador pessoa jurídica.
Consequences: §6, §9 (T-010 reescrita). O formato do XML da DPS (§5) não muda: são outros elementos do mesmo leiaute v1.01. Fica aberto o que o Não Optante emite em `totTrib` (Q-14).

### DEC-014: Certificado autoassinado nos testes, o do cliente só em scripts manuais; INV-05 (2026-10-08, T-013)
Context: Q-03 a/b. O certificado do cliente é a identidade jurídica dele e não pode ir ao git (INV-03), então a CI e outras máquinas não o têm. O autoassinado não conecta na API, que só aceita ICP-Brasil. O `README.md` lista o mTLS como o maior risco do projeto.
Decision: do humano, na conversa de 2026-10-08: (a) os testes automatizados usam sempre um autoassinado gerado por eles; na T-004 um script manual abre o certificado do cliente e mostra só titular, CNPJ e validade; uma task nova (T-015) faz um teste de conexão mTLS em produção restrita, com consulta que não emite nada, antes da T-005. (b) dados fictícios nos testes e nada de senha ou conteúdo de certificado em log vira o INV-05.
Alternatives: só o autoassinado até a T-007 (rejeitado: adia a descoberta de um problema de mTLS); usar o certificado do cliente desde a T-004 sem o teste de conexão antecipado.
Consequences: §4 (INV-05, ainda sem teste até a T-004), §7, §9 (T-004 desbloqueada, T-015 criada, T-007 depende de T-015). A T-015 depende do `[VERIFY]` da URL base da SEFIN.

### DEC-015: Modelo próprio, signxml e httpx (2026-10-08, T-013)
Context: Q-06. O `README.md` listava nfelib, signxml ou lxml+xmlsec, e httpx ou requests.
Decision: do humano, na conversa de 2026-10-08: manter as dataclasses próprias (confirma a DEC-001); signxml para a assinatura; httpx para HTTP e mTLS.
Alternatives: nfelib (rejeitado: dependência nova e reescrita de `src/dps.py`); lxml+xmlsec (rejeitado: binário nativo no Windows); requests (rejeitado: precisa do PFX em PEM no disco ou de `requests-pkcs12`).
Consequences: §6, §9. A escolha do signxml é condicional: o perfil de assinatura do padrão nacional ainda é `[VERIFY]`; se o signxml não o produzir, a T-005 volta ao humano. Nenhuma das bibliotecas foi instalada nem teve versão, licença ou API conferida.

### DEC-016: Milestones M1 a M4 e escopo da fase (2026-10-08, T-013)
Context: Q-07. Os milestones eram inferidos; o brainstorming do `README.md` tem dois passos que o objetivo da fase não citava.
Decision: do humano, na conversa de 2026-10-08: M1 DPS gerada e válida offline, com sucesso = G-1 e G-2 passando e T-010 e T-014 `done`; M2 assinada e empacotada; M3 transmitida por mTLS em produção restrita, com a NFS-e de retorno decodificada; M4, fora desta fase, consulta por chave e DANFSe.
Alternatives: incluir consulta e DANFSe nesta fase; terminar a fase na resposta do servidor, sem decodificar o retorno.
Consequences: §1, §9. A T-007 passa a incluir a decodificação do retorno.

### DEC-017: Boundaries B-1 a B-3 (2026-10-08, T-013)
Context: Q-08. Não havia boundaries; os módulos de certificado e de rede ainda não existem.
Decision: do humano, na conversa de 2026-10-08: aprovar as três propostas, com teste em G-1 que confira os imports de `src/`.
Alternatives: aprovar sem teste; não definir até existir `client.py`.
Consequences: §3, §9 (T-016). Lista de exceções vazia.

### DEC-018: Repositório público, sem licença; XSDs mantidos (2026-10-08, T-013)
Context: Q-10. O repositório é público, não tem `LICENSE` e versiona os XSDs oficiais. A página de origem declara o conteúdo do site sob CC BY-ND 3.0, que permite redistribuir sem alteração e com crédito.
Decision: do humano, na conversa de 2026-10-08: manter público e sem licença. Os XSDs continuam versionados; `schemas/LEIAME.md` passa a citar a licença e o pacote de origem.
Alternatives: público com MIT; tornar privado (a CI em Windows passaria a consumir minutos do plano).
Consequences: §7. Sem `LICENSE`, terceiros não têm permissão de uso do código. INV-01 e o `.gitignore` de `schemas/*-local/` passam a sustentar também a condição "sem derivações": a cópia sem âncoras não é distribuída. Que o aviso do site cobre o pacote de schemas é leitura do agente. Q-09 foi fechada na mesma conversa sem decisão nova: o brainstorming do `README.md` fica como está.

### DEC-019: `serie` restrita a 1–49999 (2026-10-08, T-013)
Context: Q-12. O Anexo I reserva 00001 a 49999 ao aplicativo próprio e rejeita o resto com E0010; o modelo aceita até 99999.
Decision: do humano, na conversa de 2026-10-08: restringir no modelo, numa task pequena (T-014).
Alternatives: manter 1–99999 e deixar a faixa por conta de quem chama.
Consequences: §6, §9 (T-014). O formato de `serie` no XML ("1" ou "00001") segue aberto em Q-11.

### DEC-020: Ordem das próximas tasks, revista (2026-10-08, T-013)
Context: a DEC-009 fixava T-003, T-010, T-006, T-004, T-005, T-007. Surgiram T-014 a T-018, e o humano decidiu que o teste de conexão mTLS (T-015) vem logo depois da T-004 e antes da T-005 (DEC-014). O `README.md` aponta o mTLS como o maior risco do projeto, e um problema ali (certificado vencido ou não aceito, URL errada, cadastro do emitente) pode depender de terceiros e levar dias.
Decision: T-017, T-003, T-016, T-004, T-015, T-010, T-014, T-018, T-006, T-005, T-007. Proposta pelo agente a pedido do humano, que a confirmou na conversa de 2026-10-08; a posição relativa da T-015 já era decisão dele. Razões: T-017 e T-003 primeiro, porque são pequenas e tudo o que vem depois já nasce com a documentação no repositório, formatado e com CI; T-016 antes da T-004, para o teste de boundaries existir quando entrar o primeiro módulo de certificado; T-004 e T-015 antes do trabalho no modelo, para descobrir cedo se a conexão funciona; T-010, T-014 e T-018 juntas, porque mexem no mesmo arquivo e fecham o M1; T-006 e T-005 depois, porque só fazem falta para a T-007.
Alternatives: fechar o M1 antes de tocar em certificado (a primeira proposta do agente nesta data; rejeitada por ele mesmo na revisão: adia o maior risco em favor de tasks de resultado previsível); seguir o menor ID elegível (rejeitado pela DEC-009).
Consequences: §9. Substitui a ordem da DEC-009. Os milestones deixam de ser executados em sequência: parte de M2 e de M3 (T-004, T-015) acontece antes de M1 fechar. Continua valendo que task bloqueada espera e que o humano pode nomear outra.

### DEC-021: Versionar a documentação oficial do governo (2026-10-08, T-013)
Context: `docs/referencia/` é ignorada no git e guarda, juntos, os anexos e manuais oficiais (cerca de 1,9 MB) e a nota fiscal do cliente, que tem dados reais. O spec e o `docs/SOURCES.md` citam o Anexo I e os manuais, que quem clona o repositório não recebe; a página oficial só publica a documentação atual. `docs/SOURCES.md` cita `docs/referencia/gov-docs/`, mas nesta máquina os arquivos estão direto em `docs/referencia/`.
Decision: do humano, na conversa de 2026-10-08: versionar os documentos oficiais em `docs/referencia/gov-docs/`, sem alteração, como área frozen, com `LEIAME.md` de origem e licença; o resto de `docs/referencia/` continua ignorado; um gate impede rastrear arquivos dali fora de `gov-docs/`. Execução na T-017.
Alternatives: manter tudo fora do git (rejeitado: as citações do spec ficam sem como conferir e os arquivos precisam ser levados à mão); versionar a pasta inteira (rejeitado: publicaria a nota do cliente).
Consequences: §9 (T-017). Na T-017: §5 ganha uma área frozen, §8 um gate, e o `.gitignore` muda. A licença é a CC BY-ND 3.0 da página de origem, com a mesma ressalva da DEC-018.

### DEC-022: O modelo recusa Não Optante e MEI por enquanto (2026-10-08, T-013)
Context: Q-14. O Anexo I proíbe `indTotTrib` para Não Optante, e o código o emite para todos. O cliente da PoC é ME/EPP. O XML de uma NFS-e real dele, emitida pelo emissor web oficial, usa `pTotTribSN` e `regApTribSN`, o que confirma a DEC-013.
Decision: do humano, na conversa de 2026-10-08: o modelo recusa `op_simp_nac` 1 e 2 com erro claro, até existir um emitente desses. Nenhum dado da nota do cliente é escrito no repositório, que é público; os dados reais do prestador ficam em arquivo local fora do git.
Alternatives: implementar já `pTotTrib` ou `vTotTrib` para o Não Optante (rejeitado: sem caso de uso na PoC); manter `indTotTrib` para todos (rejeitado: o servidor rejeitaria).
Consequences: §6, §9 (T-010, critério 6). Os testes existentes que usam Não Optante ou MEI precisam mudar na T-010. Ficam abertas Q-15 e Q-16.

### DEC-023: Task própria para os campos opcionais que o cliente usa (2026-10-08, T-013)
Context: Q-16. A DPS real do cliente tem `cTribMun`, `tribFed/piscofins` (`CST`, `tpRetPisCofins`), `fone` e `email`, que o modelo não gera. No Anexo I os quatro são opcionais (ocorrência 0-1), e nas regras desses campos não há obrigatoriedade para o perfil do cliente.
Decision: do humano, na conversa de 2026-10-08: task própria (T-018), depois da T-010. Escopo e acceptance criteria redigidos pelo agente.
Alternatives: incluir na T-010 (rejeitado: a T-010 corrige o que o servidor rejeitaria; estes campos são opcionais); deixar de fora (rejeitado: a nota emitida pelo aplicativo ficaria com menos informação que as atuais do cliente).
Consequences: §6, §9 (T-018). O formato do XML da DPS (§5) não muda. Se o contador exige esses campos nas notas é pergunta para ele, junto com a Q-15.

### DEC-024: Produto para vários emitentes; perfil da carteira; INV-06 (2026-10-08, T-013)
Context: o spec descrevia o produto sem dizer para quantas empresas, e várias decisões desta data (DEC-013, DEC-014, DEC-022) foram justificadas por "o cliente", no singular. O humano esclareceu que o sistema emite para várias empresas, cada uma com o seu certificado, e trouxe respostas dos contadores sobre o perfil da carteira (§1). O código de `src/` já recebe tudo do emitente como parâmetro; a configuração, não: o `.env` tem um único certificado.
Decision: do humano, na conversa de 2026-10-08: (a) o produto é multi-emitente, com uma lista de certificados; (b) a primeira versão do modelo atende só ME/EPP com apuração pelo Simples; Não Optante, MEI e pessoa física não existem na carteira e são recusados; ISS por fora é raro e fica recusado até a T-023; (c) construção civil, serviço em outro município e tomador no exterior existem na carteira e viram tasks (T-020 a T-022); (d) cancelamento e substituição entram depois da emissão, em M4; (e) INV-06: nada de emitente fixo no código.
Alternatives: suportar já os três regimes do Simples (rejeitado: não há emitente fora de ME/EPP); suportar ISS por fora na T-010 (rejeitado: caso raro, regras ainda não lidas); cancelamento e substituição dentro desta fase (rejeitado: a PoC primeiro prova que emite).
Consequences: §1, §4 (INV-06, ainda sem teste), §7, §9 (T-010 e T-004 ajustadas; T-019 a T-023 criadas). A DEC-022 continua valendo no resultado, com outra razão: a carteira é só ME/EPP, não "o cliente é ME/EPP". Onde as DECs desta data dizem "o cliente", leia-se o primeiro emitente, cujo certificado e nota de exemplo temos. Q-15 respondida; abertas Q-17 e Q-18.

### DEC-025: Acréscimos à ordem das tasks (2026-10-08, T-013)
Context: a DEC-020 foi confirmada antes de existirem T-019 a T-023.
Decision: proposta pelo agente e confirmada pelo humano na conversa de 2026-10-08: T-019 entra antes da T-004, porque a T-004 já deve receber o certificado por emitente; T-020 a T-023 ficam depois da T-007, porque a primeira transmissão usa o caso simples e prova o caminho inteiro antes de o modelo crescer. Ordem completa: T-017, T-003, T-016, T-019, T-004, T-015, T-010, T-014, T-018, T-006, T-005, T-007, e depois T-020 a T-023.
Alternatives: ampliar o modelo (T-020 a T-023) antes da primeira transmissão (rejeitado: mais código sem saber se o servidor aceita o caso simples).
Consequences: §9. O resto da DEC-020 não muda.

### DEC-026: Manifesto SHA-256 para a documentação oficial; regra de referência privada no G-4 (2026-10-08, T-017)
Context: a T-017 pede a pasta `docs/referencia/gov-docs/` como frozen, conferida por gate, e um gate que impeça rastrear o resto de `docs/referencia/`. G-3 compara com `main` e, na branch que acrescenta os arquivos, acusa os próprios acréscimos.
Decision: do agente (escolhas de implementação): (a) manifesto `SHA256SUMS` na pasta e `tests/test_gov_docs.py`, em G-1, que falha se um arquivo mudar, sumir ou aparecer sem estar no manifesto; G-3 também passa a listar a pasta; (b) a regra de referência privada entra em `src/segredos.py`, na mesma função `proibidos` que o G-4 já usa, em vez de um script novo; (c) `.gitignore` troca `docs/referencia/` por `docs/referencia/*` mais a exceção `!docs/referencia/gov-docs/`, porque o git não reinclui nada dentro de uma pasta ignorada inteira; (d) `.gitattributes` marca `*.pdf` e `*.xlsx` como binários, para a conversão de fim de linha nunca alterar os arquivos e quebrar o manifesto.
Alternatives: só G-3 (rejeitado: não aponta qual arquivo mudou nem pega um arquivo estranho na pasta, e falha na própria branch da task); um gate G-6 separado para a referência privada (rejeitado: mesma lógica e mesma entrada do G-4).
Consequences: §3, §5, §7, §8. O nome `segredos` passa a cobrir também material com dados reais, que não é segredo no sentido de INV-03. Trocar um documento oficial exige mudar o manifesto no mesmo commit, o que fica visível na revisão. Os arquivos não foram comparados com os que a página oficial publica hoje: `[VERIFY: procedência dos arquivos de gov-docs]`, como o dos XSDs. Antes de versionar, os metadados foram conferidos: autores e datas de modificação são anteriores à entrega ao projeto, e os comentários embutidos no Anexo I são notas técnicas da própria planilha.

## §11 Open questions

| ID | Question | Blocks |
|---|---|---|
| Q-01 | **Respondida em 2026-10-07: os quatro aprovados, ver §4 e DEC-004.** Aprovar, ajustar ou rejeitar cada candidato a invariant de §4 (C-1 schemas oficiais intocados; C-2 default homologação; C-3 certificados e senhas fora do git; C-4 `Id` com 45 caracteres). Para C-2: basta o default, ou `producao` deve exigir uma confirmação explícita extra (ou ser recusado nesta fase, dado DEC-002)? | T-001, todas |
| Q-02 | **Respondida em 2026-10-07, ver §5 e DEC-005.** O que fica frozen em §5: `schemas/1.01`? também `schemas/1.00` (não usado), ou removê-lo? As pastas vazias `schemas/Componente_Schemas` e `schemas/Componente_recepcao` (não rastreadas) têm algum uso? | T-001 |
| Q-03 | **Respondida em 2026-10-08, ver DEC-014 e INV-05:** (a) testes com autoassinado, o certificado do cliente só em scripts manuais (T-004, T-015, T-007); (b) sim, como invariant. Texto anterior: **Parcial em 2026-10-07:** o humano confirmou que `lika-2026.pfx` é o certificado do cliente e que o titular autorizou o uso em produção restrita. Faltam duas respostas: (a) desenvolver T-004 e T-005 com certificado autoassinado de teste, deixando o do cliente só para T-007? (b) só dados fictícios nos testes automatizados e nunca senha ou conteúdo de certificado em logs? Texto original: Certificado: `certs/lika-2026.pfx` já existe e o `.env` tem senha, mas o contexto dizia que ainda não há A1. É o certificado do cliente? Há autorização do titular para uso em homologação? Onde a DPS de teste pode ser emitida (CNPJ do titular)? Como tratar dados reais em `out/` e em logs? | T-004, T-007 |
| Q-04 | **Respondida em 2026-10-07: (a), ver DEC-003.** T-001, abordagem: (a) cópia gerada `schemas/1.01-local`, ignorada no git, com script e teste de diferença mínima (seu plano; recomendo, restringindo a remoção às âncoras de início/fim); (b) corrigir em memória ao carregar o esquema, sem arquivo derivado. Em (a), `scripts/preparar_xsd.py` (não rastreado) entra como base? E `.gitignore` ganha `schemas/*-local/`? | T-001 |
| Q-05 | **Respondida em 2026-10-08, ver DEC-012:** ruff, e CI no GitHub Actions em Windows. O lock já era pip-tools (DEC-011). Texto anterior: **Parcial em 2026-10-07:** lock com pip-tools, ver DEC-011. Seguem abertos o formatador e linter e a CI (T-003). Texto original: Ferramentas a adicionar: lock (pip-tools, uv, `pip freeze` com hashes), formatador e linter (ex.: ruff), CI (GitHub Actions; há remoto `origin` no GitHub). | T-002, T-003 |
| Q-06 | **Respondida em 2026-10-08, ver DEC-015:** modelo próprio; signxml, condicionada ao `[VERIFY]` do perfil de assinatura; httpx. Texto anterior: Bibliotecas: nfelib só para bindings da DPS, ou manter o modelo próprio? Assinatura: signxml ou lxml+xmlsec? HTTP: httpx ou requests? | T-005, T-007 |
| Q-07 | **Respondida em 2026-10-08, ver DEC-016:** M1 a M3 confirmados; a decodificação do retorno entra em M3; consulta por chave e DANFSe viram M4, fora desta fase. Texto anterior: Escopo e milestones: M1–M3 de §9 estão certos? Os passos 4 e 5 do README (decodificar retorno; consulta por chave e DANFSe) entram nesta fase? Critério de sucesso de M1 proposto: "G-1 e G-2 passam, com o teste de XSD rodando". | planejamento |
| Q-08 | **Respondida em 2026-10-08, ver §3 e DEC-017:** aprovadas, com teste (T-016). Texto anterior: Boundaries de §3. Proposta: `src/dps.py` não depende de rede nem de certificado; só `client.py` faz I/O de rede; `scripts/` depende de `src/`, nunca o contrário. | T-004 em diante |
| Q-09 | **Respondida em 2026-10-08:** o brainstorming fica como está, no fim do README, marcado como histórico. Texto anterior: **Parcial em 2026-10-08:** o README ganhou as seções de uso (T-012) e o brainstorming ficou no fim, marcado como histórico, com a ressalva de pydantic. Segue aberto se o brainstorming deve ser reescrito ou removido. Texto original: Conflitos com o README: cita pydantic (contra DEC-001) e é um brainstorming, não uma descrição do projeto. Atualizar numa task própria? | – |
| Q-10 | **Respondida em 2026-10-08, ver DEC-018:** repositório público, sem licença; os XSDs ficam versionados, sob a CC BY-ND 3.0 da página de origem. Texto anterior: Licença: não há `LICENSE`. O remoto é `github.com/prbn021/nfse-poc`; se for público, o repositório redistribui os XSDs oficiais. Qual licença, e os XSDs podem ficar versionados? | cópia de código de terceiros |
| Q-11 | **Parcial em 2026-10-07:** o defeito do XSD fica só registrado no spec (§8, DEC-003), sem reporte. O formato segue aberto: o Anexo I diz apenas "numérico, tamanho 1-5"; confirmar na primeira transmissão em produção restrita. Texto original: Formato de `serie` no XML ("1" ou "00001") e a quem reportar o defeito do padrão no XSD oficial (se quiser reportar). | T-007 |
| Q-12 | **Respondida em 2026-10-08, ver DEC-019:** sim, na T-014. Texto anterior: Restringir `serie` no modelo a 1–49999? O Anexo I reserva essa faixa ao aplicativo próprio e rejeita o resto com E0010; `Dps` hoje aceita até 99999. | – |
| Q-13 | **Respondida em 2026-10-08, ver DEC-013:** (a) `pTotTribSN`; (b) sim, o Anexo I o torna obrigatório para ME/EPP; (c) sim. Texto anterior: Emitente ME/EPP: (a) qual opção de `totTrib` emitir no lugar de `indTotTrib` (`pTotTribSN`, ou `vTotTrib`/`pTotTrib`)? (b) emitir `regApTribSN`, que o modelo hoje não tem? (c) o exemplo e os testes devem espelhar o perfil do cliente (ME/EPP, tomador pessoa física, sem inscrição municipal), sempre com dados fictícios (liga com Q-03b)? | T-010 |
| Q-14 | **Respondida em 2026-10-08, ver DEC-022:** o modelo recusa Não Optante e MEI por enquanto. Texto anterior: Emitente Não Optante: o Anexo I proíbe `indTotTrib` e `pTotTribSN`, e o código hoje emite `indTotTrib`. O que emitir: `pTotTrib` (três percentuais) ou `vTotTrib` (três valores)? Ou o modelo recusa Não Optante por enquanto, já que o cliente é ME/EPP? O mesmo vale para MEI, que pode manter `indTotTrib`. | T-010, critério do Não Optante |
| Q-15 | **Respondida em 2026-10-08 pelos contadores:** o percentual é calculado sobre o faturamento e muda com frequência; quem o informa é a própria equipe de contabilidade, a partir das declarações de faturamento. No sistema é dado de entrada por emitente e por competência (DEC-024); como ele chega até o sistema é a Q-18. Texto anterior: De onde vem o percentual de `pTotTribSN` a cada emissão (alíquota efetiva do Simples no mês, outra referência?) e quem o informa. Perguntar ao contador do cliente. No código é um parâmetro. | Primeira transmissão real (T-007); não bloqueia a T-010 |
| Q-16 | **Respondida em 2026-10-08, ver DEC-023:** task própria, T-018; os quatro campos são opcionais no Anexo I. Texto anterior: A DPS real do cliente tem campos que o modelo não gera: `cTribMun`, `tribFed/piscofins` (`CST`, `tpRetPisCofins`), `fone` e `email` do prestador. Entram na T-010, viram task própria ou ficam de fora? Recomendação do agente: task própria, depois de conferir no Anexo I quais são obrigatórios para esse perfil. | T-007 |
| Q-17 | Guarda de certificados e senhas de vários emitentes no produto: onde ficam, quem tem acesso, como cada titular autoriza o uso e como se revoga. Na PoC ficam em arquivos locais fora do git (T-019). | Produto; não bloqueia a PoC |
| Q-18 | Como o percentual de `pTotTribSN` de cada emitente e competência entra no sistema: digitado a cada mês, importado das declarações de faturamento, ou outro meio? E o que fazer quando falta o percentual da competência: recusar a emissão? | Produto; na PoC é argumento do script |
