# SOURCES

Fatos externos checados e código copiado. "XSD local" significa os arquivos em `schemas/1.01` deste repositório, cuja procedência ainda é um item `[VERIFY]` (SPEC §6).

## Facts
| Date       | Fact                          | Value  | Version | Source  |
|------------|-------------------------------|--------|---------|---------|
| 2026-10-07 | Regex de `xs:pattern` é ancorada implicitamente no início e no fim; `^` e `$` não são metacaracteres (`^` só é especial dentro de grupo de caracteres) | Metacaracteres: `.` `\` `?` `*` `+` `{` `}` `(` `)` `[` `]` | XML Schema Part 2: Datatypes, 2ª ed. (2004), Apêndice F | https://www.w3.org/TR/xmlschema-2/#regexs |
| 2026-10-07 | libxml2 trata `^` e `$` em `xs:pattern` como literais | `^0{0,4}\d{1,5}$` rejeita `1` e `00001`, aceita `^1$` e `^00001$` | lxml 6.1.3 / libxml2 2.11.9 | Experimento local com `etree.XMLSchema` (esquema mínimo), `.venv` do projeto |
| 2026-10-07 | Padrões com âncoras nos XSDs | 1 de 54 em `schemas/1.01` (`TSSerieDPS`, `tiposSimples_v1.01.xsd:161`); 0 em `schemas/1.00` (pasta removida em 2026-10-08, T-009) | XSD local v1.01 / v1.00 | `grep` nos arquivos locais |
| 2026-10-07 | DPS de exemplo contra o XSD com o padrão de `serie` sem âncoras | 0 erros | XSD local v1.01 | Cópia temporária fora do repositório, `src.dps.validar_xml` |
| 2026-10-07 | `Id` da DPS | 45 posições, padrão `DPS[0-9]{42}`: "DPS" + Cód.Mun (7) + Tipo de Inscrição Federal (1) + Inscrição Federal (14) + Série (5) + Núm. DPS (15) | XSD local v1.01 | `tiposSimples_v1.01.xsd`, `TSIdDPS` |
| 2026-10-07 | `opSimpNac` | 1 Não Optante; 2 MEI; 3 ME/EPP | XSD local v1.01 | `tiposSimples_v1.01.xsd`, `TSOpSimpNac` |
| 2026-10-07 | `regEspTrib` | 0 Nenhum; 1 Ato Cooperado; 2 Estimativa; 3 Microempresa Municipal; 4 Notário ou Registrador; 5 Profissional Autônomo; 6 Sociedade de Profissionais; 9 Outros | XSD local v1.01 | `tiposSimples_v1.01.xsd`, `TSRegEspTrib` |
| 2026-10-07 | `tribISSQN` | 1 Operação tributável; 2 Imunidade; 3 Exportação de serviço; 4 Não Incidência | XSD local v1.01 | `tiposSimples_v1.01.xsd`, `TSTribISSQN` |
| 2026-10-07 | `tpRetISSQN` | 1 Não Retido; 2 Retido pelo Tomador; 3 Retido pelo Intermediário | XSD local v1.01 | `tiposSimples_v1.01.xsd`, `TSTipoRetISSQN` |
| 2026-10-07 | `tpAmb` | 1 Produção; 2 Homologação | XSD local v1.01 | `tiposSimples_v1.01.xsd`, `TSTipoAmbiente` |
| 2026-10-07 | `nDPS` | até 15 dígitos, padrão `[1-9]{1}[0-9]{0,14}` | XSD local v1.01 | `tiposSimples_v1.01.xsd`, `TSNumDPS` |
| 2026-10-07 | Início de `infDPS` (sequência) | `tpAmb`, `dhEmi`, `verAplic`, `serie`, `nDPS`, `dCompet`, `tpEmit`, `cMotivoEmisTI`?, `chNFSeRej`?, `cLocEmi`, … | XSD local v1.01 | `tiposComplexos_v1.01.xsd`, `TCInfDPS` |
| 2026-10-07 | Tipo de Inscrição Federal no `Id` da DPS | 1 = CPF do emitente; 2 = CNPJ do emitente. Divergência entre o `Id` e os campos: rejeição E0004 | Anexo I v1.01 (2026-02-09) | Anexo I, aba `LEIAUTE DPS_NFS-e`, campo `id`; aba `RN DPS_NFS-e`, E0004 |
| 2026-10-07 | Faixas de `serie` da DPS | 00001 a 49999 aplicativo próprio; 50000 a 69999 emissor móvel; 70000 a 79999 emissor web; 80000 a 89999 transcrição manual (web). Fora da faixa do emissor: rejeição E0010. Leiaute: numérico, tamanho 1-5 (não diz se há zeros à esquerda no XML) | Anexo I v1.01 (2026-02-09) | Anexo I, aba `LEIAUTE DPS_NFS-e`, campo `serie`; aba `RN DPS_NFS-e`, E0010 |
| 2026-10-07 | `indTotTrib` com emitente ME/EPP | Se o emitente for ME/EPP no Simples Nacional na data de competência, `indTotTrib` nunca pode ser informado: rejeição E0712 (nível 1) | Anexo I v1.01 (2026-02-09) | Anexo I, aba `RN DPS_NFS-e`, E0712 |
| 2026-10-07 | Opções do grupo `totTrib` (escolha) | `vTotTrib` (federais, estaduais, municipais em R$), `pTotTrib` (os mesmos em %), `indTotTrib` (0 = Não), `pTotTribSN` (% da alíquota do Simples Nacional) | Anexo I v1.01 (2026-02-09) | Anexo I, aba `LEIAUTE DPS_NFS-e`, grupo `valores/trib/totTrib` |
| 2026-10-07 | `regApTribSN` | Opcional (0-1); não pode ser preenchido quando `opSimpNac` = 1 ou 2: rejeição E0162 | Anexo I v1.01 (2026-02-09) | Anexo I, aba `LEIAUTE DPS_NFS-e` e aba `RN DPS_NFS-e`, E0162 |
| 2026-10-07 | Regras de recepção da DPS (área de dados) | Falha ao decodificar Base64: E1225; estrutura descompactada malformada: E1226; prefixo de namespace não permitido: E1228; XML fora de UTF-8: E1229; falha no esquema XML: E1235 | Anexo I v1.01 (2026-02-09) | Anexo I, aba `RN_RECEPCAO_DPS` |
| 2026-10-07 | Rotas da API da Sefin Nacional (Emissor Público) | `POST /nfse` (recepção síncrona da DPS); `GET /nfse/{chaveAcesso}`; `GET /dps/{id}` e `HEAD /dps/{id}`; `POST`/`GET /nfse/{chaveAcesso}/eventos`. O manual não traz a URL base | Manual dos Contribuintes, Emissor Público Nacional (histórico interno: 1.0, 17/03/2025) | `manual-contribuintes-emissor-publico-api-sistema-nacional-nfs-e-v1-2-out2025.pdf`, seções 1.3 a 1.5 |
| 2026-10-07 | Swagger do ambiente de produção restrita | `https://adn.producaorestrita.nfse.gov.br/contribuintes/docs/index.html` (link citado nos manuais; não acessado) | Manuais dos Contribuintes: Emissor Público (1.0, 17/03/2025) e ADN (1.0, 12/02/2026) | `manual-contribuintes-emissor-publico-…-v1-2-out2025.pdf`, seção 1.6; `manual-contribuintes-apis-adn-sistema-nacional-nfse.pdf`, seção 1.2 |
| 2026-10-07 | Opções do `pip-compile` usadas nos locks | `--generate-hashes`, `--strip-extras`, `--allow-unsafe`, `-o/--output-file` existem e fazem o descrito; com `--allow-unsafe` o lock inclui `pip` e `setuptools` | pip-tools 7.6.2 | `python -m piptools compile --help` da versão instalada; execução local |
| 2026-10-07 | Instalação com `--require-hashes` a partir dos dois locks | Código de saída 0 num clone novo com `py -3.11 -m venv`; 51 testes passam | pip 24.0 (do venv novo), Python 3.11.9, Windows | Execução local em diretório temporário |
| 2026-10-08 | `totTrib` conforme a situação no Simples Nacional | Não Optante: `indTotTrib` e `pTotTribSN` nunca podem ser informados. MEI: `pTotTribSN` nunca pode ser informado. ME/EPP: `indTotTrib` nunca pode ser informado | Anexo I v1.01 (2026-02-09) | Anexo I, textos das regras (lidos em `xl/sharedStrings.xml` da planilha; aba e código de rejeição não anotados, exceto E0712 para ME/EPP) |
| 2026-10-08 | Obrigatoriedade de `regApTribSN` | Obrigatório quando `opSimpNac` = 3; não pode ser preenchido quando `opSimpNac` = 1 ou 2. Complementa a linha de 2026-10-07: o XSD o declara opcional, a regra de negócio o exige para ME/EPP | Anexo I v1.01 (2026-02-09) | Anexo I, textos das regras (código de rejeição da obrigatoriedade não anotado) |
| 2026-10-08 | Valores de `regApTribSN` | 1 tributos federais e municipal pelo SN; 2 federais pelo SN e ISSQN por fora do SN; 3 federais e municipal por fora do SN | XSD local v1.01 | `tiposSimples_v1.01.xsd`, `TSRegimeApuracaoSimpNac` |
| 2026-10-08 | Licença do conteúdo da página de origem dos XSDs | "Todo o conteúdo deste site está publicado sob a licença Creative Commons Atribuição-SemDerivações 3.0 Não Adaptada" (rodapé; aponta para https://creativecommons.org/licenses/by-nd/3.0/deed.pt_BR) | Página em 2026-10-08 | https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/documentacao-atual (lida por ferramenta de busca do agente, que resumiu a página; o texto do rodapé veio citado) |
| 2026-10-08 | Pacote de schemas listado na página de origem | `NFSe-ESQUEMAS_XSD-v1.01-20260209` (`…/documentacao-atual/nfse-esquemas_xsd-v1-01-20260209.zip`); não baixado nem comparado com `schemas/1.01` | Página em 2026-10-08 | Mesma página |
| 2026-10-08 | Visibilidade do repositório no GitHub | Público: `https://github.com/prbn021/nfse-poc` responde 200 sem autenticação | – | `curl` sem credenciais |
| 2026-10-08 | Opção de `totTrib` e `regTrib` numa NFS-e real de emitente ME/EPP | `totTrib` com `pTotTribSN`; `regTrib` com `opSimpNac`, `regApTribSN`, `regEspTrib`, nessa ordem | Leiaute 1.01, `EmissorWeb_1.6.0.0` | XML da nota de exemplo do cliente, em `docs/referencia/` (fora do git; tem dados reais, nenhum transcrito aqui) |
| 2026-10-08 | Campos presentes na DPS dessa nota | Além dos que o modelo já gera: `cTribMun`, `tribFed/piscofins` (`CST`, `tpRetPisCofins`), `fone` e `email` em `prest`; tomador só com `CPF` e `xNome`; prestador sem `IM`; `nDPS` sem zeros à esquerda; DPS sem `Signature` | Leiaute 1.01, `EmissorWeb_1.6.0.0` | Mesmo arquivo |
| 2026-10-08 | Assinatura da NFS-e devolvida pelo sistema nacional | `rsa-sha256`; digest `sha256`; `xml-exc-c14n#WithComments`; transformações `enveloped-signature` e `xml-exc-c14n#WithComments`; `X509Certificate` em `KeyInfo`; referência ao `Id` de `infNFSe` | Leiaute 1.01 | Mesmo arquivo. É a assinatura do sistema sobre a NFS-e, não a da DPS pelo contribuinte |
| 2026-10-08 | `cTribMun`, `prest/fone`, `prest/email`, `tribFed`, `tribFed/piscofins` | Todos com ocorrência 0-1. Dentro de `piscofins`: `CST` 1-1, `tpRetPisCofins` 0-1. Regras: `cTribMun` informado precisa existir e ser administrado pelo município de incidência, exceto MEI (E0314); `email` com estrutura de e-mail (E0148); `tribFed` proibido para emitente pessoa física (E0675) | Anexo I v1.01 (2026-02-09) | Anexo I, abas `LEIAUTE DPS_NFS-e` (linhas 137, 138, 195, 312 a 320) e `RN DPS_NFS-e` (linhas 221, 222, 318, 514 a 523) |

"Anexo I" é `docs/referencia/gov-docs/anexo_i-sefin_adn-dps_nfse-snnfse-v1-01-20260209.xlsx`; os manuais estão na mesma pasta. `docs/referencia/` é ignorada no git: os arquivos foram entregues pelo humano em 2026-10-07 e a URL de download de cada um não foi registrada. O manual do Emissor Público tem `v1-2-out2025` no nome do arquivo, mas o histórico de versões interno traz só "1.0, 17/03/2025".

### SHA-256 dos XSDs em `schemas/1.01` (primeiros 16 hex, 2026-10-07, commit `4abfc2c`)

| Arquivo | SHA-256 (prefixo) |
|---|---|
| CNC_v1.00.xsd | 7032188bb6f137d5 |
| DPS_v1.01.xsd | fe45e5250a48e519 |
| NFSe_v1.01.xsd | af0bd2d8c50acba3 |
| evento_v1.01.xsd | 986d0a1c4d27454f |
| pedRegEvento_v1.01.xsd | e90b6816d29cca0b |
| tiposCnc_v1.00.xsd | af606b7317824fa8 |
| tiposComplexos_v1.01.xsd | e8e09d525574cc22 |
| tiposEventos_v1.01.xsd | 1b32bea21089dc23 |
| tiposSimples_v1.01.xsd | 830ea116c34d7310 |
| xmldsig-core-schema.xsd | 49848f732663aecb |

## Copied code
| Date       | Our path            | Origin (URL + commit) | License | Task  |
|------------|---------------------|-----------------------|---------|-------|
| (antes de 2026-10-07) | `schemas/1.01/*.xsd` (`schemas/1.00/*.xsd` veio do mesmo pacote e foi removido em 2026-10-08, T-009) | Pacote de schemas do Portal Nacional da NFS-e, segundo `schemas/LEIAME.md` (https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/documentacao-atual). Data de download e versão do pacote não registradas. | CC BY-ND 3.0, declarada no rodapé da página de origem para o conteúdo do site (checado em 2026-10-08; SPEC DEC-018) | anterior ao Bootstrap |
