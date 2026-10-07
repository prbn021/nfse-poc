# SOURCES

Fatos externos checados e código copiado. "XSD local" significa os arquivos em `schemas/1.01` deste repositório, cuja procedência ainda é um item `[VERIFY]` (SPEC §6).

## Facts
| Date       | Fact                          | Value  | Version | Source  |
|------------|-------------------------------|--------|---------|---------|
| 2026-10-07 | Regex de `xs:pattern` é ancorada implicitamente no início e no fim; `^` e `$` não são metacaracteres (`^` só é especial dentro de grupo de caracteres) | Metacaracteres: `.` `\` `?` `*` `+` `{` `}` `(` `)` `[` `]` | XML Schema Part 2: Datatypes, 2ª ed. (2004), Apêndice F | https://www.w3.org/TR/xmlschema-2/#regexs |
| 2026-10-07 | libxml2 trata `^` e `$` em `xs:pattern` como literais | `^0{0,4}\d{1,5}$` rejeita `1` e `00001`, aceita `^1$` e `^00001$` | lxml 6.1.3 / libxml2 2.11.9 | Experimento local com `etree.XMLSchema` (esquema mínimo), `.venv` do projeto |
| 2026-10-07 | Padrões com âncoras nos XSDs | 1 de 54 em `schemas/1.01` (`TSSerieDPS`, `tiposSimples_v1.01.xsd:161`); 0 em `schemas/1.00` | XSD local v1.01 / v1.00 | `grep` nos arquivos locais |
| 2026-10-07 | DPS de exemplo contra o XSD com o padrão de `serie` sem âncoras | 0 erros | XSD local v1.01 | Cópia temporária fora do repositório, `src.dps.validar_xml` |
| 2026-10-07 | `Id` da DPS | 45 posições, padrão `DPS[0-9]{42}`: "DPS" + Cód.Mun (7) + Tipo de Inscrição Federal (1) + Inscrição Federal (14) + Série (5) + Núm. DPS (15) | XSD local v1.01 | `tiposSimples_v1.01.xsd`, `TSIdDPS` |
| 2026-10-07 | `opSimpNac` | 1 Não Optante; 2 MEI; 3 ME/EPP | XSD local v1.01 | `tiposSimples_v1.01.xsd`, `TSOpSimpNac` |
| 2026-10-07 | `regEspTrib` | 0 Nenhum; 1 Ato Cooperado; 2 Estimativa; 3 Microempresa Municipal; 4 Notário ou Registrador; 5 Profissional Autônomo; 6 Sociedade de Profissionais; 9 Outros | XSD local v1.01 | `tiposSimples_v1.01.xsd`, `TSRegEspTrib` |
| 2026-10-07 | `tribISSQN` | 1 Operação tributável; 2 Imunidade; 3 Exportação de serviço; 4 Não Incidência | XSD local v1.01 | `tiposSimples_v1.01.xsd`, `TSTribISSQN` |
| 2026-10-07 | `tpRetISSQN` | 1 Não Retido; 2 Retido pelo Tomador; 3 Retido pelo Intermediário | XSD local v1.01 | `tiposSimples_v1.01.xsd`, `TSTipoRetISSQN` |
| 2026-10-07 | `tpAmb` | 1 Produção; 2 Homologação | XSD local v1.01 | `tiposSimples_v1.01.xsd`, `TSTipoAmbiente` |
| 2026-10-07 | `nDPS` | até 15 dígitos, padrão `[1-9]{1}[0-9]{0,14}` | XSD local v1.01 | `tiposSimples_v1.01.xsd`, `TSNumDPS` |
| 2026-10-07 | Início de `infDPS` (sequência) | `tpAmb`, `dhEmi`, `verAplic`, `serie`, `nDPS`, `dCompet`, `tpEmit`, `cMotivoEmisTI`?, `chNFSeRej`?, `cLocEmi`, … | XSD local v1.01 | `tiposComplexos_v1.01.xsd`, `TCInfDPS` |

### SHA-256 dos XSDs em `schemas/1.01` (primeiros 16 hex, 2026-10-07, commit `7709aee`)

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
| (antes de 2026-10-07) | `schemas/1.00/*.xsd`, `schemas/1.01/*.xsd` | Pacote de schemas do Portal Nacional da NFS-e, segundo `schemas/LEIAME.md` (https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/documentacao-atual). Data de download e versão do pacote não registradas. | Não informada (SPEC Q-10) | anterior ao Bootstrap |
